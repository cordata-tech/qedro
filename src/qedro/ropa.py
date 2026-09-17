"""The Art. 30 projection.

Turns a stream of OpenLineage events into a record of processing activities:
one activity per job, with the purpose and lawful basis that job declared, the
datasets it read and wrote, and — the part that distinguishes this from every
register maintained by hand — **where each field came from**.

That last part is the whole design. A purpose emitted as a facet by the pipeline
that ran is evidence. The same string typed into `qedro.yaml` is an assertion.
Both are useful and they are not the same thing, so :class:`Sourced` carries the
value and its :class:`Provenance` together and nothing downstream can print one
without the other being available. The tombstone falls out of that rather than
being decided separately.

Two things this module is careful not to do:

**It does not reject evidence.** A legal basis outside the vocabulary is
reported and flagged, never dropped. Refusing to read what an emitter actually
sent would hide the finding that matters.

**It does not claim to be the whole record.** Art. 30 covers every processing
activity a controller runs, and pipelines are a subset of that. :class:`Scope`
exists to say so on every run — see cordata-tech/qedro#3.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from . import scope, words
from .config import Config, Controller, Rule
from .events import Event
from .mark import Completeness
from .sources import ReadReport
from .vocabulary import Vocabulary

if TYPE_CHECKING:  # declared.py builds on Provenance and Sourced from here
    from .declared import Declared

#: The job facet the Art. 30 fields travel in. Published as a spec in
#: `schemas/openlineage-art30-processing-facet.json`.
FACET = "processing"


class Provenance(StrEnum):
    """Where a field's value came from. Ordered worst-last on purpose.

    ``FACET`` is the pipeline saying what it does, in the same event that proves
    it ran. ``MAPPING`` is a human saying what a pipeline does, in a file that
    nothing verifies. ``DECLARED`` is a human saying what processing with no
    lineage at all does — weaker than a mapping, because a mapped job at least
    emitted events proving it ran. ``ABSENT`` is nobody having said.
    """

    FACET = "facet"
    MAPPING = "mapping"
    DECLARED = "declared"
    ABSENT = "absent"

    @property
    def evidenced(self) -> bool:
        return self is Provenance.FACET


@dataclass(frozen=True)
class Sourced:
    """A value and where it came from, kept together so neither can be used
    without the other being at hand."""

    value: str = ""
    provenance: Provenance = Provenance.ABSENT
    unrecognised: bool = False

    def __bool__(self) -> bool:
        return bool(self.value)

    @property
    def evidenced(self) -> bool:
        return self.provenance.evidenced and bool(self.value)


@dataclass(frozen=True)
class Activity:
    """One processing activity — one job, across every event that named it."""

    namespace: str
    name: str
    domain: str
    purpose: Sourced
    legal_basis: Sourced
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    runs: int = 0
    events: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    #: False when a mapping rule's `domain:` named the domain. See #9.
    domain_guessed: bool = True

    @property
    def key(self) -> str:
        return f"{self.namespace}/{self.name}"

    @property
    def evidenced(self) -> bool:
        """Both Art. 30 fields came from an emitted facet."""
        return self.purpose.evidenced and self.legal_basis.evidenced

    def gaps(self) -> list[str]:
        """Why this activity is not fully evidenced, in a reviewer's words."""
        out = []
        for label, sourced in (("purpose", self.purpose), ("legal basis", self.legal_basis)):
            if not sourced.value:
                out.append(f"no {label} declared")
            elif sourced.provenance is Provenance.MAPPING:
                out.append(f"{label} came from the mapping file, not from an emitted facet")
            if sourced.unrecognised:
                out.append(f"{sourced.value!r} is not a {label} the vocabulary defines")
        return out


@dataclass(frozen=True)
class Scope(scope.Scope):
    """What the Art. 30 run looked at.

    The window, the source and the domains live in the base; what is added
    here is what *coverage* means for this projection — how many jobs, how
    many datasets, and how the provenance of their fields divided up.
    """

    jobs: int = 0
    datasets: int = 0
    namespaces: tuple[str, ...] = ()
    evidenced: int = 0
    from_mapping: int = 0
    undeclared: int = 0
    #: Activities declared with no lineage. Counted apart from everything above,
    #: which describes what was looked at — a declared activity was written
    #: down, not looked at. See cordata-tech/qedro#6.
    declared: int = 0
    #: Jobs that were looked at and not listed as activities, because they are
    #: orchestration parents — see `_parents`. Named rather than counted, so the
    #: omission is itself visible. See cordata-tech/qedro#8.
    parents: tuple[str, ...] = ()

    #: Unconditional, per #3, and worded to be true whether or not anything is
    #: declared. Printing it only when nothing was declared would make it
    #: conditional; keeping the earlier wording beside declared entries would
    #: make it false. See the decision on cordata-tech/qedro#6.
    OUT_OF_VIEW = (
        "This record covers processing performed by pipelines that emit lineage, and any "
        "activities declared with no lineage. Systems that do not emit lineage — CRM, HR, "
        "ticketing, marketing tools, anything on paper — are not represented here unless "
        "they are declared, a declared activity is an assertion rather than evidence, and "
        "the absence of anything else from this record is not evidence of its absence "
        "from the organisation."
    )

    def lines(self) -> tuple[tuple[str, str], ...]:
        out = [
            ("in view", f"{self.jobs} jobs, {self.datasets} datasets, {self.events} events"),
        ]
        if self.namespaces:
            out.append(("namespaces", ", ".join(self.namespaces)))
        out.append(
            (
                "provenance",
                (
                    f"{self.evidenced} evidenced, {self.from_mapping} from the mapping "
                    f"file, {self.undeclared} undeclared"
                ),
            )
        )
        if self.parents:
            n = len(self.parents)
            out.append(
                (
                    "parents",
                    (
                        f"{n} {words.plural(n, 'job', 'jobs')} not listed as "
                        f"{words.plural(n, 'an activity', 'activities')} — "
                        f"{words.plural(n, 'a parent run', 'parent runs')} with no datasets "
                        f"and no processing facet: {', '.join(self.parents)}"
                    ),
                )
            )
        if self.declared:
            out.append(
                (
                    "declared",
                    (
                        f"{self.declared} {words.plural(self.declared, 'activity', 'activities')} "
                        "declared with no lineage"
                    ),
                )
            )
        return tuple(out)


@dataclass
class Record:
    """The Art. 30 record: a controller, the activities, and the scope."""

    controller: Controller
    activities: tuple[Activity, ...] = ()
    scope: Scope = field(default_factory=Scope)
    completeness: Completeness = field(default_factory=Completeness)
    vocabulary: str = ""
    generated_from: str = ""
    #: Processing that emits no lineage, as somebody declared it. Kept out of
    #: `activities` so nothing that iterates over those — counts, domains, the
    #: deployer view's use cases — can take a declared entry for an evidenced one.
    declared: tuple[Declared, ...] = ()

    @property
    def complete(self) -> bool:
        return self.completeness.complete

    def by_legal_basis(self) -> dict[str, list[Activity]]:
        out: dict[str, list[Activity]] = {}
        for activity in self.activities:
            out.setdefault(activity.legal_basis.value or "not declared", []).append(activity)
        return out


def build(
    events: Iterable[Event],
    *,
    config: Config,
    vocabulary: Vocabulary,
    report: ReadReport | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    declared: Sequence[Declared] = (),
) -> Record:
    """Project events into an Art. 30 record, with any declared activities beside it."""
    grouped: dict[str, list[Event]] = {}
    for event in events:
        grouped.setdefault(event.job.key, []).append(event)

    parents = _parents(grouped)
    activities = tuple(
        _activity(job_events, config=config, vocabulary=vocabulary)
        for key, job_events in sorted(grouped.items())
        if key not in parents
    )

    scope = _scope(
        activities,
        config=config,
        report=report,
        since=since,
        until=until,
        declared=len(declared),
        parents={key: grouped[key] for key in parents},
    )
    completeness = _completeness(
        activities,
        controller=config.controller,
        scope=scope,
        report=report,
        declared=len(declared),
    )

    return Record(
        controller=config.controller,
        activities=activities,
        scope=scope,
        completeness=completeness,
        vocabulary=vocabulary.name,
        generated_from=report.origin if report else "",
        declared=tuple(declared),
    )


def _activity(events: Sequence[Event], *, config: Config, vocabulary: Vocabulary) -> Activity:
    first = events[0]
    rule = config.rule_for(first.job.namespace, first.job.name)

    facet = first.job_facet(FACET) or {}
    # A job's facet can arrive on any of its events and an emitter may attach it
    # to COMPLETE but not START. Take the first event that carries it rather
    # than assuming the first event does.
    if not facet:
        for event in events:
            candidate = event.job_facet(FACET)
            if candidate:
                facet = candidate
                break

    purpose = _sourced("purpose", facet, rule, vocabulary)
    legal_basis = _sourced("legal_basis", facet, rule, vocabulary)

    times = [e.event_time for e in events if e.event_time is not None]
    runs = {e.run.run_id for e in events if e.run.run_id}
    inputs = {d.key for e in events for d in e.inputs}
    outputs = {d.key for e in events for d in e.outputs}

    return Activity(
        namespace=first.job.namespace,
        name=first.job.name,
        domain=config.domain_for(first.job.namespace, rule),
        domain_guessed=config.domain_guessed(rule),
        purpose=purpose,
        legal_basis=legal_basis,
        inputs=tuple(sorted(inputs)),
        outputs=tuple(sorted(outputs)),
        runs=len(runs),
        events=len(events),
        first_seen=min(times) if times else None,
        last_seen=max(times) if times else None,
    )


def _sourced(
    key: str, facet: Mapping[str, object], rule: Rule | None, vocabulary: Vocabulary
) -> Sourced:
    """Facet first, mapping second, nothing third. The order is the point."""
    emitted = facet.get(key)
    if isinstance(emitted, str) and emitted.strip():
        value = emitted.strip()
        return Sourced(value, Provenance.FACET, vocabulary.unrecognised(key, value))

    mapped = getattr(rule, key, "") if rule else ""
    if isinstance(mapped, str) and mapped:
        return Sourced(mapped, Provenance.MAPPING, vocabulary.unrecognised(key, mapped))

    return Sourced("", Provenance.ABSENT)


def _parents(grouped: Mapping[str, Sequence[Event]]) -> tuple[str, ...]:
    """Jobs that are orchestration parents rather than processing.

    dbt emits a job for the invocation and one per model, and each model's run
    names the invocation's run in the standard `ParentRunFacet`. Listing the
    invocation as its own Art. 30 activity adds a row that reads and writes
    nothing and can never be evidenced. See cordata-tech/qedro#8.

    A job is a parent only when all three hold:

    - a run in view names one of its runs as parent, matched on
      `ParentRunFacet.run.runId` — the emitter's own statement of the
      relationship, not a guess from the job name;
    - it read and wrote no datasets in the window, so a parent that also
      processes data stays listed;
    - it carries no `processing` facet, so a declaration made on a parent is
      never hidden by tidying the row away.

    Nothing here reads dbt's `jobType` values or its `dbt-run-` naming, so an
    Airflow DAG run or a Spark application run is treated the same way. A
    backend that drops the `parent` facet — Snowflake's external lineage does —
    leaves the invocation listed, which is the behaviour before this rule and
    not a wrong answer.
    """
    parent_runs: set[str] = set()
    for job_events in grouped.values():
        for event in job_events:
            facet = event.run_facet("parent") or {}
            run = facet.get("run")
            if isinstance(run, Mapping) and isinstance(run.get("runId"), str):
                parent_runs.add(run["runId"])

    out = []
    for key, job_events in grouped.items():
        runs = {e.run.run_id for e in job_events if e.run.run_id}
        if not runs & parent_runs:
            continue
        if any(e.inputs or e.outputs for e in job_events):
            continue
        if any(e.job_facet(FACET) for e in job_events):
            continue
        out.append(key)
    return tuple(sorted(out))


def _scope(
    activities: Sequence[Activity],
    *,
    config: Config,
    report: ReadReport | None,
    since: datetime | None,
    until: datetime | None,
    declared: int = 0,
    parents: Mapping[str, Sequence[Event]] | None = None,
) -> Scope:
    parents = parents or {}
    # A parent's events were looked at, so they count toward the window even
    # though the job is not listed.
    times = [t for a in activities for t in (a.first_seen, a.last_seen) if t is not None]
    times += [e.event_time for evs in parents.values() for e in evs if e.event_time is not None]
    datasets = {d for a in activities for d in a.inputs + a.outputs}

    return Scope(
        source=report.origin if report else "",
        # The resolved window, not the arguments as typed: with no `--since`,
        # what was actually covered starts at the earliest event that arrived.
        since=since if since is not None else (min(times) if times else None),
        until=until if until is not None else (max(times) if times else None),
        events=report.events if report else sum(a.events for a in activities),
        jobs=len(activities) + len(parents),
        datasets=len(datasets),
        namespaces=tuple(sorted({a.namespace for a in activities})),
        domains_declared=config.domains,
        domains_seen=tuple(sorted({a.domain for a in activities if a.domain})),
        domains_guessed=tuple(
            sorted({a.domain for a in activities if a.domain and a.domain_guessed})
        ),
        domains_mapped=tuple(
            sorted({a.domain for a in activities if a.domain and not a.domain_guessed})
        ),
        evidenced=sum(1 for a in activities if a.evidenced),
        from_mapping=sum(
            1
            for a in activities
            if Provenance.MAPPING in (a.purpose.provenance, a.legal_basis.provenance)
        ),
        undeclared=sum(1 for a in activities if not a.purpose or not a.legal_basis),
        declared=declared,
        parents=tuple(sorted(parents)),
    )


def _completeness(
    activities: Sequence[Activity],
    *,
    controller: Controller,
    scope: Scope,
    report: ReadReport | None,
    declared: int = 0,
) -> Completeness:
    """When the artefact may claim to stand on its own evidence.

    Every condition here is a reason the mark is withheld, and each is phrased
    for the reader of the artefact rather than for whoever is debugging it.
    Withholding is the signal; do not make this unconditional.
    """
    completeness = Completeness()

    if report is not None:
        for reason in report.reasons():
            completeness = completeness.degraded(reason)

    # Art. 30(1)(a). A record that does not name its controller is not an
    # Art. 30 record at all, so this is a hole in the artefact rather than a
    # missing nicety — and it is invisible in the output unless said.
    if not controller:
        completeness = completeness.degraded(
            "no controller is declared, and Art. 30(1)(a) requires one — "
            "set `controller:` in qedro.yaml"
        )

    # Before the early return below, so a record made only of declared
    # activities still says why it is no proof rather than only that no
    # lineage was found.
    if declared:
        completeness = completeness.degraded(
            f"{declared} {words.plural(declared, 'activity is', 'activities are')} declared "
            f"with no lineage, so {words.plural(declared, 'it is', 'they are')} asserted — "
            f"nothing in the events shows that {words.plural(declared, 'it', 'they')} happened"
        )

    if not activities:
        return completeness.degraded(
            "no processing activities were found — nothing was recorded, "
            "which is not the same as nothing having happened"
        )

    total = len(activities)

    mapped = [a for a in activities if not a.evidenced and (a.purpose or a.legal_basis)]
    if mapped:
        n = len(mapped)
        completeness = completeness.degraded(
            f"{n} of {total} {words.plural(total, 'activity', 'activities')} "
            f"{words.plural(n, 'relies', 'rely')} on the mapping file rather than on an emitted "
            f"facet, so {words.plural(n, 'that entry is', 'those entries are')} asserted rather "
            "than proven"
        )

    silent_fields = [a for a in activities if not a.purpose or not a.legal_basis]
    if silent_fields:
        n = len(silent_fields)
        completeness = completeness.degraded(
            f"{n} of {total} {words.plural(total, 'activity', 'activities')} "
            f"{words.plural(n, 'has', 'have')} no purpose or no legal basis from any source"
        )

    unrecognised = [a for a in activities if a.purpose.unrecognised or a.legal_basis.unrecognised]
    if unrecognised:
        n = len(unrecognised)
        completeness = completeness.degraded(
            f"{n} {words.plural(n, 'activity carries', 'activities carry')} "
            "a value the vocabulary does not define"
        )

    if scope.domains_silent:
        completeness = completeness.degraded(scope.silent_reason())

    return completeness
