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

from . import scope, words
from .config import Config, Controller, Rule
from .events import Event
from .mark import Completeness
from .sources import ReadReport
from .vocabulary import Vocabulary

#: The job facet the Art. 30 fields travel in. Published as a spec in
#: `schemas/openlineage-art30-processing-facet.json`.
FACET = "processing"


class Provenance(StrEnum):
    """Where a field's value came from. Ordered worst-last on purpose.

    ``FACET`` is the pipeline saying what it does, in the same event that proves
    it ran. ``MAPPING`` is a human saying what a pipeline does, in a file that
    nothing verifies. ``ABSENT`` is nobody having said.
    """

    FACET = "facet"
    MAPPING = "mapping"
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

    OUT_OF_VIEW = (
        "This record covers processing performed by pipelines that emit lineage. "
        "Systems that do not emit lineage — CRM, HR, ticketing, marketing tools, "
        "anything on paper — are not represented here, and their absence from this "
        "record is not evidence of their absence from the organisation."
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
) -> Record:
    """Project events into an Art. 30 record."""
    grouped: dict[str, list[Event]] = {}
    for event in events:
        grouped.setdefault(event.job.key, []).append(event)

    activities = tuple(
        _activity(job_events, config=config, vocabulary=vocabulary)
        for _, job_events in sorted(grouped.items())
    )

    scope = _scope(activities, config=config, report=report, since=since, until=until)
    completeness = _completeness(
        activities, controller=config.controller, scope=scope, report=report
    )

    return Record(
        controller=config.controller,
        activities=activities,
        scope=scope,
        completeness=completeness,
        vocabulary=vocabulary.name,
        generated_from=report.origin if report else "",
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


def _scope(
    activities: Sequence[Activity],
    *,
    config: Config,
    report: ReadReport | None,
    since: datetime | None,
    until: datetime | None,
) -> Scope:
    times = [t for a in activities for t in (a.first_seen, a.last_seen) if t is not None]
    datasets = {d for a in activities for d in a.inputs + a.outputs}

    return Scope(
        source=report.origin if report else "",
        # The resolved window, not the arguments as typed: with no `--since`,
        # what was actually covered starts at the earliest event that arrived.
        since=since if since is not None else (min(times) if times else None),
        until=until if until is not None else (max(times) if times else None),
        events=report.events if report else sum(a.events for a in activities),
        jobs=len(activities),
        datasets=len(datasets),
        namespaces=tuple(sorted({a.namespace for a in activities})),
        domains_declared=config.domains,
        domains_seen=tuple(sorted({a.domain for a in activities if a.domain})),
        evidenced=sum(1 for a in activities if a.evidenced),
        from_mapping=sum(
            1
            for a in activities
            if Provenance.MAPPING in (a.purpose.provenance, a.legal_basis.provenance)
        ),
        undeclared=sum(1 for a in activities if not a.purpose or not a.legal_basis),
    )


def _completeness(
    activities: Sequence[Activity],
    *,
    controller: Controller,
    scope: Scope,
    report: ReadReport | None,
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
        completeness = completeness.degraded(
            f"declared in scope but produced no lineage in the window: "
            f"{', '.join(scope.domains_silent)}"
        )

    return completeness
