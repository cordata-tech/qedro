"""The deployer view of the Art. 30 record.

`qedro ropa <source> --view deployer` answers, per AI use case, the questions the
AI Act puts to a *deployer* — the organisation using a model somebody else built —
from the same events the Art. 30 record is built from: which inputs a run read,
for what purpose and on what lawful basis, which model version ran, and how much
of the run record is actually in view. See cordata-tech/qedro#7.

**This is a view of the record, not a second projection of the events.** It is
built from the :class:`~qedro.ropa.Record` that `ropa` produces, and each use
case holds the *same* :class:`~qedro.ropa.Activity` — the same purpose and legal
basis objects, with the same provenance. So the Art. 30 record and this view
cannot disagree about why something ran or on what basis, because neither
restates it. The events are consulted only for what the Art. 30 record does not
carry: the model version per run, and which run read what.

Three things this module is careful about:

**It does not decide whether a use case is high-risk.** The deployer duties in
Art. 26 apply to Annex III high-risk systems, from 2 December 2027 (Regulation
(EU) 2024/1689 as amended by Regulation (EU) 2026/1744; cited as the consolidated
text, CELEX 02024R1689-20260727, verified 2026-09-16). Nothing in the events says
whether a system is in Annex III, so every rendering states the condition rather
than implying the duty applies.

**Retention is what the records evidence, never a compliant period.** The events
carry no retention policy. What can be shown is the span of run records in view,
which is a lower bound on what the source kept — or, when `--since` or `--until`
was given, only the width of the query. Art. 26(6) sets a minimum for logs a
deployer controls while DSGVO Art. 5(1)(e) storage limitation pulls the other way
for personal data, and this view shows the span without resolving either. A
short span does not withhold the mark: doing so would imply Art. 26(6) applies
today.

**Declared use cases are marked as declared.** Processing with no lineage —
staff using a vendor's assistant through its UI — is most AI use outside
engineering teams, and it enters from a declared-activities document
(:mod:`qedro.declared`). Every field of such an entry is an assertion, and any
declared entry withholds the mark.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from . import scope as scope_module
from . import words
from .config import Controller
from .declared import Declared
from .events import Event
from .mark import Completeness
from .ropa import Activity, Provenance, Record
from .sources import ReadReport

#: How every rendering names the law it refers to. One text, cited once.
REGULATION = "Regulation (EU) 2024/1689 (AI Act), consolidated text CELEX 02024R1689-20260727"

#: The condition every Art. 26 reference carries. Stated, never implied. Two
#: sentences kept apart so a renderer can print them as separate lines, which
#: stops a wrap from splitting the date.
APPLIES_FROM = "Art. 26 applies from 2 December 2027 to deployers of Annex III high-risk systems."
NOT_DECIDED = "Whether any use case here is high-risk is not decided by this view."
APPLICATION = f"{APPLIES_FROM} {NOT_DECIDED}"

#: The key a run reports its model version under.
MODEL_KEY = "model_version"

#: Where a model version is looked for, in order. `cordata_provenance` is where
#: `pipeline-runtime` puts it (`step_params.<step>.model_version`, verified
#: against an emitted event on 2026-09-17). `tags` is the standard OpenLineage
#: run facet, where any client can add a `model_version` entry. There is no
#: standard facet for this, so the list is short and documented rather than a
#: guess at every key that might mean it.
MODEL_SOURCES = ("cordata_provenance", "tags")

#: Six months, in days, for comparing a span of records against Art. 26(6)'s
#: minimum. A comparison, not a verdict — see the module docstring.
SIX_MONTHS = 183


@dataclass(frozen=True)
class ModelVersion:
    """One model version, across the runs that reported it."""

    version: str
    reported_by: str
    runs: int
    first_seen: datetime | None = None
    last_seen: datetime | None = None


@dataclass(frozen=True)
class LatestRun:
    """The most recent run of a use case, and what it read."""

    run_id: str
    when: datetime | None
    model_version: str
    inputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class UseCase:
    """An activity from the Art. 30 record whose runs reported a model version."""

    activity: Activity
    models: tuple[ModelVersion, ...]
    latest: LatestRun
    runs_without_model: int = 0

    @property
    def key(self) -> str:
        return self.activity.key

    @property
    def span_days(self) -> int | None:
        """Days between the oldest and newest run record in view."""
        first, last = self.activity.first_seen, self.activity.last_seen
        if first is None or last is None:
            return None
        return (last - first).days


@dataclass(frozen=True)
class Scope(scope_module.Scope):
    """What the deployer view looked at."""

    activities: int = 0
    use_cases: int = 0
    declared: int = 0
    runs: int = 0
    #: True when `--since` or `--until` cut the query, in which case the span of
    #: records in view says nothing about how long the source retains them.
    windowed: bool = False

    OUT_OF_VIEW = (
        "This view lists the activities in the Art. 30 record whose runs reported a "
        "model version, and use cases declared with no lineage. An AI use that emits "
        "no lineage and is not declared is not represented here. The retention shown "
        "is the span of run records in view, not the source's retention policy, which "
        "the events do not carry. Art. 26(6) sets a minimum period for logs under a "
        "deployer's control while DSGVO Art. 5(1)(e) storage limitation pulls the "
        "other way for personal data, and this view resolves neither."
    )

    def lines(self) -> tuple[tuple[str, str], ...]:
        out = [
            (
                "in view",
                (
                    f"{self.use_cases} of {self.activities} activities reported a model "
                    f"version, {self.declared} declared, {self.events} events"
                ),
            ),
            ("runs", f"{words.count(self.runs, 'run')} of the listed use cases"),
        ]
        if self.windowed:
            out.append(
                (
                    "retention",
                    (
                        "the window was limited by --since or --until, so the span of "
                        "records shows the query, not what the source retains"
                    ),
                )
            )
        return tuple(out)


@dataclass
class DeployerRecord:
    """The deployer view: use cases from lineage, declared use cases, and scope."""

    controller: Controller
    use_cases: tuple[UseCase, ...] = ()
    declared: tuple[Declared, ...] = ()
    scope: Scope = field(default_factory=Scope)
    completeness: Completeness = field(default_factory=Completeness)
    vocabulary: str = ""
    regulation: str = REGULATION
    application: str = APPLICATION

    @property
    def complete(self) -> bool:
        return self.completeness.complete


def build(
    record: Record,
    events: Iterable[Event],
    *,
    declared: Sequence[Declared] = (),
    report: ReadReport | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> DeployerRecord:
    """The deployer view of an Art. 30 record, from the events it was built from."""
    by_job: dict[str, list[Event]] = {}
    for event in events:
        by_job.setdefault(event.job.key, []).append(event)

    use_cases = tuple(
        found
        for activity in record.activities
        if (found := _use_case(activity, by_job.get(activity.key, []))) is not None
    )

    scope = Scope(
        source=record.scope.source,
        since=record.scope.since,
        until=record.scope.until,
        events=record.scope.events,
        # This view makes no claim about domain coverage — that is the Art. 30
        # view's finding — so declared domains are not carried into it.
        domains_declared=(),
        domains_seen=(),
        activities=len(record.activities),
        use_cases=len(use_cases),
        declared=len(declared),
        runs=sum(u.activity.runs for u in use_cases),
        windowed=since is not None or until is not None,
    )

    return DeployerRecord(
        controller=record.controller,
        use_cases=use_cases,
        declared=tuple(declared),
        scope=scope,
        completeness=_completeness(
            use_cases, declared, controller=record.controller, report=report
        ),
        vocabulary=record.vocabulary,
    )


def _use_case(activity: Activity, events: Sequence[Event]) -> UseCase | None:
    runs: dict[str, list[Event]] = {}
    for event in events:
        if event.run.run_id:
            runs.setdefault(event.run.run_id, []).append(event)

    per_run = {run_id: _model(found) for run_id, found in runs.items()}
    if not any(version for version, _ in per_run.values()):
        return None

    versions: dict[tuple[str, str], list[datetime | None]] = {}
    for run_id, (version, reported_by) in per_run.items():
        if version:
            versions.setdefault((version, reported_by), []).append(_when(runs[run_id]))

    models = tuple(
        sorted(
            (
                ModelVersion(
                    version=version,
                    reported_by=reported_by,
                    runs=len(times),
                    first_seen=min((t for t in times if t), default=None),
                    last_seen=max((t for t in times if t), default=None),
                )
                for (version, reported_by), times in versions.items()
            ),
            key=lambda m: (m.last_seen is not None, m.last_seen),
            reverse=True,
        )
    )

    latest_id = max(runs, key=lambda run_id: (_when(runs[run_id]) is not None, _when(runs[run_id])))
    latest_events = runs[latest_id]
    return UseCase(
        activity=activity,
        models=models,
        latest=LatestRun(
            run_id=latest_id,
            when=_when(latest_events),
            model_version=per_run[latest_id][0],
            inputs=tuple(sorted({d.key for e in latest_events for d in e.inputs})),
        ),
        runs_without_model=sum(1 for version, _ in per_run.values() if not version),
    )


def _model(events: Sequence[Event]) -> tuple[str, str]:
    """The model version a run reported, and the facet that reported it."""
    for name in MODEL_SOURCES:
        for event in events:
            facet = event.run_facet(name)
            if not facet:
                continue
            found = _versions(name, facet)
            if found:
                return ", ".join(found), name
    return "", ""


def _versions(name: str, facet: Mapping[str, object]) -> list[str]:
    found: set[str] = set()
    if name == "tags":
        tags = facet.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, Mapping) and tag.get("key") == MODEL_KEY:
                    value = tag.get("value")
                    if isinstance(value, str) and value.strip():
                        found.add(value.strip())
    else:
        params = facet.get("step_params")
        if isinstance(params, Mapping):
            for step in params.values():
                if isinstance(step, Mapping):
                    value = step.get(MODEL_KEY)
                    if isinstance(value, str) and value.strip():
                        found.add(value.strip())
    return sorted(found)


def _when(events: Sequence[Event]) -> datetime | None:
    times = [e.event_time for e in events if e.event_time is not None]
    return max(times) if times else None


def _completeness(
    use_cases: Sequence[UseCase],
    declared: Sequence[Declared],
    *,
    controller: Controller,
    report: ReadReport | None,
) -> Completeness:
    """When the view may claim to stand on its own evidence.

    Deliberately absent: the span of records. A short span is reported, and
    withholding the mark for it would imply that Art. 26(6) applies today.
    """
    completeness = Completeness()

    if report is not None:
        for reason in report.reasons():
            completeness = completeness.degraded(reason)

    if not controller:
        completeness = completeness.degraded(
            "no controller is declared, and Art. 30(1)(a) DSGVO requires one — "
            "set `controller:` in qedro.yaml"
        )

    if not use_cases and not declared:
        return completeness.degraded(
            "no AI use cases were found — no run in view reported a model version, "
            "and none were declared"
        )

    total = len(use_cases)
    if total:
        mapped = [
            u
            for u in use_cases
            if Provenance.MAPPING
            in (u.activity.purpose.provenance, u.activity.legal_basis.provenance)
        ]
        if mapped:
            n = len(mapped)
            completeness = completeness.degraded(
                f"{n} of {total} {words.plural(total, 'use case', 'use cases')} "
                f"{words.plural(n, 'takes', 'take')} purpose or legal basis from the mapping "
                "file rather than an emitted facet, so those entries are asserted"
            )

        missing = [u for u in use_cases if not u.activity.purpose or not u.activity.legal_basis]
        if missing:
            n = len(missing)
            completeness = completeness.degraded(
                f"{n} of {total} {words.plural(total, 'use case', 'use cases')} "
                f"{words.plural(n, 'has', 'have')} no purpose or no legal basis from any source"
            )

        unrecognised = [
            u
            for u in use_cases
            if u.activity.purpose.unrecognised or u.activity.legal_basis.unrecognised
        ]
        if unrecognised:
            n = len(unrecognised)
            completeness = completeness.degraded(
                f"{words.count(n, 'use case')} {words.plural(n, 'carries', 'carry')} a value "
                "the vocabulary does not define"
            )

        partial = [u for u in use_cases if u.runs_without_model]
        if partial:
            n = len(partial)
            completeness = completeness.degraded(
                f"{words.count(n, 'use case')} {words.plural(n, 'has', 'have')} runs that "
                "reported no model version, so which model those runs used is not evidenced"
            )

    if declared:
        n = len(declared)
        completeness = completeness.degraded(
            f"{words.count(n, 'use case')} {words.plural(n, 'is', 'are')} declared rather "
            f"than evidenced — no run records exist for {words.plural(n, 'it', 'them')}, so "
            f"nothing shows that {words.plural(n, 'it', 'they')} happened, which model was "
            "used or what was read"
        )

    return completeness
