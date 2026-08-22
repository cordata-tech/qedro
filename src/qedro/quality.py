"""The assertion-history projection.

Turns a stream of OpenLineage events into what was actually checked about each
dataset, and when: which expectations ran, how often, how often they held, and
when one last failed.

The whole projection turns on one distinction, and it is the same shape as the
one `ropa` turns on:

    **A dataset with no failures and a dataset with no checks look identical
    in every summary anyone writes, and they are opposites.**

So `unchecked` is not an afterthought in the output, it is half the artefact.
A quality report listing four green datasets, out of a warehouse of two
hundred, is worse than no report — it is the invisible hole again, wearing a
different hat.

The evidence is the standard OpenLineage ``dataQualityAssertions`` facet, which
Great Expectations emits and anything else can. Note it is an **input** facet:
it describes one run's use of a dataset, not the dataset. That is exactly
right, and it is why this projection can speak in dates. *This table has a
unique key* is a claim; *the run on the 14th checked it and it held* is
evidence.

Nothing here has a mapping fallback. There is no honest way to assert in a
config file that a check passed, so the only two states are *checked* and
*not checked* — which makes this the simplest of the projections and the one
with the least room to mislead.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from . import scope as scope_module
from .config import Config, Controller
from .events import Dataset, Event
from .mark import Completeness
from .sources import ReadReport

#: The standard OpenLineage facet. Not ours — this one the ecosystem already
#: agreed on, which is why `quality` needs no schema published beside it.
FACET = "dataQualityAssertions"

#: Its sibling, carrying row counts and column statistics. Read for the run
#: count only; interpreting a distribution is not this tool's business.
METRICS = "dataQualityMetrics"


@dataclass(frozen=True)
class Check:
    """One assertion, as one run reported it."""

    assertion: str
    column: str
    success: bool
    job: str
    run_id: str
    when: datetime | None

    @property
    def key(self) -> tuple[str, str]:
        """What makes two checks the same expectation on different days."""
        return (self.assertion, self.column)


@dataclass(frozen=True)
class Expectation:
    """One expectation on one dataset, across the whole window."""

    assertion: str
    column: str
    runs: int = 0
    failures: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    last_failure: datetime | None = None

    @property
    def holds(self) -> bool:
        return self.failures == 0

    @property
    def describe(self) -> str:
        return f"{self.assertion} on {self.column}" if self.column else self.assertion


@dataclass(frozen=True)
class DatasetQuality:
    """Everything that was asserted about one dataset in the window."""

    key: str
    domain: str
    expectations: tuple[Expectation, ...] = ()
    asserted_by: tuple[str, ...] = ()
    runs: int = 0
    checks: int = 0
    failures: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    @property
    def holds(self) -> bool:
        return self.failures == 0

    def failing(self) -> tuple[Expectation, ...]:
        return tuple(e for e in self.expectations if not e.holds)


@dataclass(frozen=True)
class Scope(scope_module.Scope):
    """What the quality run looked at.

    `unchecked` is a count here and a list in the record, because the number
    is what a reader reacts to and the names are what they act on.
    """

    datasets: int = 0
    checked: int = 0
    unchecked: int = 0
    checks: int = 0
    failures: int = 0

    OUT_OF_VIEW = (
        "This history covers datasets for which a job emitted data-quality assertions "
        "in the window. A dataset that appears with no expectations was not checked, "
        "which is not the same as having passed — and a dataset that emits no lineage "
        "at all does not appear here in either state."
    )

    def lines(self) -> tuple[tuple[str, str], ...]:
        out = [
            ("in view", f"{self.datasets} datasets, {self.events} events"),
            ("checked", f"{self.checked} with assertions, {self.unchecked} with none"),
        ]
        if self.checks:
            held = self.checks - self.failures
            out.append(("assertions", f"{self.checks} run, {held} held, {self.failures} failed"))
        return tuple(out)


@dataclass
class Record:
    """The assertion history: what was checked, and what was not."""

    controller: Controller
    datasets: tuple[DatasetQuality, ...] = ()
    unchecked: tuple[str, ...] = ()
    scope: Scope = field(default_factory=Scope)
    completeness: Completeness = field(default_factory=Completeness)
    generated_from: str = ""

    @property
    def complete(self) -> bool:
        return self.completeness.complete

    @property
    def failing(self) -> tuple[DatasetQuality, ...]:
        return tuple(d for d in self.datasets if not d.holds)


def build(
    events: Iterable[Event],
    *,
    config: Config,
    report: ReadReport | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    domains: Sequence[str] = (),
) -> Record:
    """Project events into an assertion history."""
    checks: dict[str, list[Check]] = {}
    produced: dict[str, str] = {}
    consumed: dict[str, str] = {}
    seen: set[str] = set()

    for event in events:
        rule = config.rule_for(event.job.namespace, event.job.name)
        domain = config.domain_for(event.job.namespace, rule)
        for dataset in event.datasets:
            seen.add(dataset.key)
            for check in _checks(dataset, event):
                checks.setdefault(dataset.key, []).append(check)
        # A dataset belongs to the domain that **writes** it, not to whichever
        # job happened to be read first. `crm_curated.customers` is crm's even
        # though billing reads it every night — the producing domain owns the
        # data product, and attributing by first-touch would make a dataset's
        # domain depend on file order.
        for dataset in event.outputs:
            produced.setdefault(dataset.key, domain)
        for dataset in event.inputs:
            consumed.setdefault(dataset.key, domain)

    # A dataset nothing ever wrote is a source table: the only domain that has
    # said anything about it is the one that reads it.
    domain_of = {key: produced.get(key) or consumed.get(key, "") for key in seen}

    if domains:
        wanted = set(domains)
        seen = {k for k in seen if domain_of.get(k, "") in wanted}
        checks = {k: v for k, v in checks.items() if domain_of.get(k, "") in wanted}

    datasets = tuple(
        _dataset(key, found, domain_of.get(key, "")) for key, found in sorted(checks.items())
    )
    unchecked = tuple(sorted(seen - set(checks)))

    scope = _scope(
        datasets,
        unchecked=unchecked,
        config=config,
        domains_seen=tuple(sorted({d for k, d in domain_of.items() if k in seen and d})),
        report=report,
        since=since,
        until=until,
    )

    return Record(
        controller=config.controller,
        datasets=datasets,
        unchecked=unchecked,
        scope=scope,
        completeness=_completeness(datasets, unchecked=unchecked, scope=scope, report=report),
        generated_from=report.origin if report else "",
    )


def _checks(dataset: Dataset, event: Event) -> list[Check]:
    """The assertions one event reported about one dataset.

    Anything malformed is skipped rather than raised on — an assertion list is
    evidence, and evidence is counted, never fatal. An entry with no assertion
    name cannot be joined across days, so it cannot become an expectation.
    """
    facet = dataset.run_facet(FACET)
    if not facet:
        return []
    raw = facet.get("assertions")
    if not isinstance(raw, list):
        return []

    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("assertion")
        if not isinstance(name, str) or not name:
            continue
        column = entry.get("column")
        out.append(
            Check(
                assertion=name,
                column=column if isinstance(column, str) else "",
                # Absent `success` is treated as a failure. An assertion whose
                # outcome was not reported is not one that passed, and the
                # opposite default would quietly turn silence into green.
                success=entry.get("success") is True,
                job=event.job.key,
                run_id=event.run.run_id,
                when=event.event_time,
            )
        )
    return out


def _dataset(key: str, checks: Sequence[Check], domain: str) -> DatasetQuality:
    grouped: dict[tuple[str, str], list[Check]] = {}
    for check in checks:
        grouped.setdefault(check.key, []).append(check)

    times = [c.when for c in checks if c.when is not None]
    return DatasetQuality(
        key=key,
        domain=domain,
        expectations=tuple(_expectation(found) for _, found in sorted(grouped.items())),
        asserted_by=tuple(sorted({c.job for c in checks})),
        runs=len({c.run_id for c in checks if c.run_id}),
        checks=len(checks),
        failures=sum(1 for c in checks if not c.success),
        first_seen=min(times) if times else None,
        last_seen=max(times) if times else None,
    )


def _expectation(checks: Sequence[Check]) -> Expectation:
    times = [c.when for c in checks if c.when is not None]
    failures = [c.when for c in checks if not c.success and c.when is not None]
    return Expectation(
        assertion=checks[0].assertion,
        column=checks[0].column,
        runs=len(checks),
        failures=sum(1 for c in checks if not c.success),
        first_seen=min(times) if times else None,
        last_seen=max(times) if times else None,
        last_failure=max(failures) if failures else None,
    )


def _scope(
    datasets: Sequence[DatasetQuality],
    *,
    unchecked: Sequence[str],
    config: Config,
    domains_seen: tuple[str, ...],
    report: ReadReport | None,
    since: datetime | None,
    until: datetime | None,
) -> Scope:
    times = [t for d in datasets for t in (d.first_seen, d.last_seen) if t is not None]
    return Scope(
        source=report.origin if report else "",
        since=since if since is not None else (min(times) if times else None),
        until=until if until is not None else (max(times) if times else None),
        events=report.events if report else 0,
        domains_declared=config.domains,
        domains_seen=domains_seen,
        datasets=len(datasets) + len(unchecked),
        checked=len(datasets),
        unchecked=len(unchecked),
        checks=sum(d.checks for d in datasets),
        failures=sum(d.failures for d in datasets),
    )


def _completeness(
    datasets: Sequence[DatasetQuality],
    *,
    unchecked: Sequence[str],
    scope: Scope,
    report: ReadReport | None,
) -> Completeness:
    """When an assertion history may claim to stand on its own evidence.

    Note what is *not* here: a failing expectation does not withhold the mark.
    A failure is a finding, and a history that recorded it is doing its job —
    the mark says *this account of what was checked is complete*, not *the data
    is good*. Conflating those two would make the mark unreadable, and would
    give somebody a reason to stop emitting the assertion that fails.

    Nor does an uneven history. A weekly job asserts a seventh as often as a
    daily one, so *fewer runs than the busiest dataset* fires on every real
    estate — and a condition that always fires makes the mark meaningless in
    exactly the way printing it always would.
    """
    completeness = Completeness()

    if report is not None:
        for reason in report.reasons():
            completeness = completeness.degraded(reason)

    if not datasets and not unchecked:
        return completeness.degraded(
            "no datasets were found in the window — nothing was recorded, "
            "which is not the same as nothing having happened"
        )

    if not datasets:
        return completeness.degraded(
            f"none of the {len(unchecked)} datasets in view carry any assertions, "
            "so there is no history to report"
        )

    if unchecked:
        n = len(unchecked)
        total = scope.datasets
        completeness = completeness.degraded(
            f"{n} of {total} datasets carry no assertions at all — not checked is not "
            "the same as passed, and this history cannot speak for them"
        )

    if scope.domains_silent:
        completeness = completeness.degraded(
            f"declared in scope but produced no lineage in the window: "
            f"{', '.join(scope.domains_silent)}"
        )

    return completeness
