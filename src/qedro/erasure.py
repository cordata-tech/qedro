"""Proving an Art. 17 erasure reached what was derived from the erased data.

Art. 17 needs three things and this does exactly one of them. **Enumerating** where
a subject's data lives right now is the catalog's job; **erasing** it is an
orchestrator's, and never this tool's — read-only is a property of what the code
can reach. **Proving** it happened, and saying where the proof does not reach, is
this. See cordata-tech/qedro#4.

The third is not a small share of the problem. The failure modes are all lineage
failures: the result cache, the materialised view, the pre-computed monthly
rollup, the vector index that already ingested the row. Each is a dataset
*derived from* the one that was erased, and each is forgotten because nobody held
the descendant list. The transitive downstream closure is exactly what
OpenLineage knows and what a catalog does not, because a catalog sees current
state and derivation is not current state.

**This is `provenance` traversed the other way.** That module indexes events by
what they wrote and walks backwards to a commit; this indexes them by what they
read and walks forwards to everything downstream.

**The limit travels with the feature everywhere, including into the output.**
OpenLineage is dataset-level. This can say *this dataset descends from the erased
one and a job rewrote it afterwards*. It cannot say *this subject's rows are
gone* — that is row-level and no lineage event carries it. A tool that blurred
the two would produce exactly the artefact this project exists to argue against:
a compliance document whose holes are invisible. So the caveat is the scope
statement, printed on every run including one that earns the mark.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import scope as scope_module
from .config import Config, Controller
from .events import Event
from .mark import Completeness
from .ropa import Provenance
from .sources import ReadReport, utc
from .words import count, plural

#: How far downstream to walk before stopping and saying so. The same default as
#: `provenance`, and for the same reason: a closure over a real estate can be
#: large, and a truncated list that does not say it was truncated is the failure
#: this repository cares most about.
DEPTH = 5

#: The lifecycle states that are an erasure. `ALTER`, `CREATE` and `RENAME` are
#: the other three the standard facet defines, and a rename is not a deletion —
#: mistaking one for the other would report a proof that never happened.
ERASURES = frozenset({"DROP", "TRUNCATE", "OVERWRITE"})

#: Where the standard facet lives on a dataset. A dataset facet rather than an
#: output facet: *this table was dropped* is true of the table, not only of one
#: run's use of it.
LIFECYCLE = "lifecycleStateChange"


@dataclass(frozen=True)
class Tombstone:
    """When the erasure happened, and whether anybody proved it.

    `FACET` is an emitted `lifecycleStateChange` naming the dataset as dropped,
    truncated or overwritten. `DECLARED` is a date typed on the command line —
    usable everywhere, which is the point, and an assertion, which the record has
    to say.
    """

    dataset: str
    at: datetime | None = None
    provenance: Provenance = Provenance.ABSENT
    state: str = ""
    #: What `--since` said, when an emitted event superseded it. Kept so the
    #: record can print both: a typed date silently overriding evidence, and
    #: evidence silently overriding what the operator asked for, are each worse
    #: than saying the two disagree.
    asserted_at: datetime | None = None

    @property
    def evidenced(self) -> bool:
        return self.provenance is Provenance.FACET

    def describe(self) -> str:
        if self.at is None:
            return "no erasure instant"
        if self.evidenced:
            return f"{self.at.isoformat()} — emitted {self.state.lower()}"
        return f"{self.at.isoformat()} — from --since, not emitted"


@dataclass(frozen=True)
class Descendant:
    """One dataset derived from the erased one, and what happened to it since."""

    dataset: str
    depth: int
    #: The job whose run derived it from upstream. Named so a reader who has to
    #: go and rewrite this dataset knows what to run.
    through: str = ""
    #: The most recent completed run that wrote it after the tombstone.
    rewritten: datetime | None = None
    runs_since: int = 0
    #: Runs that started after the tombstone and never reported completion. Not
    #: the same as not rewritten, and not the same as rewritten.
    incomplete: int = 0
    truncated: bool = False

    @property
    def reached(self) -> bool:
        """Whether the erasure demonstrably propagated this far."""
        return self.rewritten is not None


@dataclass(frozen=True)
class Scope(scope_module.Scope):
    """What the erasure run looked at, and what it could never have looked at."""

    dataset: str = ""
    descendants: int = 0
    rewritten: int = 0
    not_rewritten: int = 0
    incomplete: int = 0
    truncated: int = 0
    depth_limit: int = DEPTH
    tombstone: Tombstone = field(default_factory=lambda: Tombstone(dataset=""))

    OUT_OF_VIEW = (
        "This record covers datasets, not rows. It can show that a dataset descends "
        "from the erased one and that a job rewrote it after the erasure; it cannot "
        "show that a particular data subject's rows are gone, because no lineage event "
        "carries that. A dataset rewritten since the erasure is one whose contents were "
        "replaced by a job that read the erased source — evidence that the erasure was "
        "propagated, not proof that it was complete."
    )

    def lines(self) -> tuple[tuple[str, str], ...]:
        out = [
            ("erased", self.dataset or "unknown"),
            ("tombstone", self.tombstone.describe()),
            ("in view", f"{count(self.descendants, 'descendant')}, {self.events} events"),
        ]
        if self.tombstone.asserted_at is not None:
            out.append(
                (
                    "superseded",
                    (
                        f"--since said {self.tombstone.asserted_at.isoformat()}; the "
                        "emitted event is what the descendants were measured against"
                    ),
                )
            )
        reached = (
            f"{self.rewritten} of {self.descendants} rewritten since the tombstone, "
            f"{self.not_rewritten} not"
        )
        out.append(("propagation", reached))
        unresolved = []
        if self.incomplete:
            unresolved.append(
                f"{count(self.incomplete, 'descendant')} reached through a run that "
                "never reported completion"
            )
        if self.truncated:
            unresolved.append(f"{self.truncated} stopped at the depth limit of {self.depth_limit}")
        if unresolved:
            out.append(("unresolved", "; ".join(unresolved)))
        return tuple(out)


@dataclass
class Record:
    """Everything derived from an erased dataset, and whether the erasure reached it."""

    controller: Controller
    dataset: str = ""
    tombstone: Tombstone = field(default_factory=lambda: Tombstone(dataset=""))
    descendants: tuple[Descendant, ...] = ()
    scope: Scope = field(default_factory=Scope)
    completeness: Completeness = field(default_factory=Completeness)
    generated_from: str = ""

    @property
    def complete(self) -> bool:
        return self.completeness.complete

    @property
    def unreached(self) -> tuple[Descendant, ...]:
        """Descendants the erasure has not demonstrably propagated to.

        The list this projection exists to produce: not a verdict, a work list.
        """
        return tuple(d for d in self.descendants if not d.reached)


def _lifecycle(dataset: Any) -> str:
    """The lifecycle state a dataset facet reports, upper-cased, or "".

    Facets are raw dictionaries, so a value that is not a string, or a facet
    that is a list because some emitter disagreed with the spec, reads as absent
    rather than raising. Parsing never raises — see `events`.
    """
    facet = dataset.facets.get(LIFECYCLE)
    if not isinstance(facet, dict):
        return ""
    state = facet.get(LIFECYCLE)
    return state.upper() if isinstance(state, str) else ""


def find_tombstone(events: Iterable[Event], dataset: str, *, since: datetime | None) -> Tombstone:
    """When the dataset was erased, from the events if anybody said so.

    An emitted `lifecycleStateChange` of `DROP`, `TRUNCATE` or `OVERWRITE` naming
    the dataset as an output is evidence of the instant. The latest one wins: an
    estate that truncates nightly has many, and the erasure being proved is the
    most recent.
    """
    found: list[tuple[datetime, str]] = []
    for event in events:
        for output in event.outputs:
            if output.key != dataset or event.event_time is None:
                continue
            # Naive is UTC, the one assumption `sources` already makes.
            # Refusing to compare would be worse, and inventing a second
            # rule here would be worse still.
            state = _lifecycle(output)
            if state in ERASURES:
                found.append((utc(event.event_time), state))

    if found:
        at, state = max(found, key=lambda pair: pair[0])
        # `since` is kept rather than dropped, so the record can say the two
        # disagree instead of quietly preferring one.
        superseded = utc(since) if since is not None and utc(since) != at else None
        return Tombstone(
            dataset=dataset,
            at=at,
            provenance=Provenance.FACET,
            state=state,
            asserted_at=superseded,
        )

    if since is not None:
        return Tombstone(dataset=dataset, at=utc(since), provenance=Provenance.DECLARED)
    return Tombstone(dataset=dataset)


def build(
    events: Iterable[Event],
    *,
    dataset: str,
    config: Config,
    report: ReadReport | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    depth: int = DEPTH,
) -> Record:
    """Walk forwards from *dataset* through everything derived from it."""
    events = list(events)
    tombstone = find_tombstone(events, dataset, since=since)

    # Indexed by what each run read, which is the one difference from
    # `provenance`: that module indexes by what runs wrote.
    consumers: dict[str, list[Event]] = {}
    for event in events:
        for source in event.inputs:
            consumers.setdefault(source.key, []).append(event)

    found: dict[str, Descendant] = {}
    seen = {dataset}
    frontier = [(dataset, 0)]

    while frontier:
        key, level = frontier.pop(0)
        for event in consumers.get(key, []):
            for output in event.outputs:
                if output.key in seen:
                    continue
                seen.add(output.key)
                truncated = level + 1 >= depth
                found[output.key] = Descendant(
                    dataset=output.key,
                    depth=level + 1,
                    through=event.job.key,
                    truncated=truncated,
                )
                if not truncated:
                    frontier.append((output.key, level + 1))

    descendants = tuple(
        sorted(
            (_measure(d, events, tombstone) for d in found.values()),
            key=lambda d: (d.depth, d.dataset),
        )
    )
    scope = _scope(
        descendants,
        dataset=dataset,
        tombstone=tombstone,
        report=report,
        since=since,
        until=until,
        depth=depth,
    )
    return Record(
        controller=config.controller,
        dataset=dataset,
        tombstone=tombstone,
        descendants=descendants,
        scope=scope,
        completeness=_completeness(
            descendants, dataset=dataset, tombstone=tombstone, scope=scope, report=report
        ),
        generated_from=report.origin if report else "",
    )


def _measure(descendant: Descendant, events: Sequence[Event], tombstone: Tombstone) -> Descendant:
    """Whether anything rewrote this dataset after the erasure.

    A completed run that wrote it counts; a run that started and never reported
    completion is counted apart, because *it may have finished* is not evidence
    and reporting it as a rewrite would be inventing the proof.
    """
    if tombstone.at is None:
        return descendant

    rewritten: datetime | None = None
    runs, incomplete = set(), set()
    for event in events:
        if event.event_time is None:
            continue
        when = utc(event.event_time)
        if when <= tombstone.at:
            continue
        if descendant.dataset not in {o.key for o in event.outputs}:
            continue
        run = event.run.run_id or f"{event.job.key}@{when.isoformat()}"
        if event.event_type == "COMPLETE":
            runs.add(run)
            if rewritten is None or when > rewritten:
                rewritten = when
        else:
            incomplete.add(run)

    return Descendant(
        dataset=descendant.dataset,
        depth=descendant.depth,
        through=descendant.through,
        rewritten=rewritten,
        runs_since=len(runs),
        incomplete=len(incomplete - runs),
        truncated=descendant.truncated,
    )


def _scope(
    descendants: Sequence[Descendant],
    *,
    dataset: str,
    tombstone: Tombstone,
    report: ReadReport | None,
    since: datetime | None,
    until: datetime | None,
    depth: int,
) -> Scope:
    # No declared domains, as `provenance` also carries none: this record is
    # about one dataset and everything derived from it, so *this domain produced
    # no lineage* is not a claim it is in a position to make. Passing them would
    # report every domain in the config as silent on every run.
    return Scope(
        source=report.origin if report else "",
        since=since,
        until=until,
        events=report.events if report else 0,
        dataset=dataset,
        descendants=len(descendants),
        rewritten=sum(1 for d in descendants if d.reached),
        not_rewritten=sum(1 for d in descendants if not d.reached),
        incomplete=sum(1 for d in descendants if d.incomplete),
        truncated=sum(1 for d in descendants if d.truncated),
        depth_limit=depth,
        tombstone=tombstone,
    )


def _completeness(
    descendants: Sequence[Descendant],
    *,
    dataset: str,
    tombstone: Tombstone,
    scope: Scope,
    report: ReadReport | None,
) -> Completeness:
    """When an erasure record may claim to stand on its own evidence.

    Four ways it cannot, and each names something a reader would have to go and
    do. The list of places the proof does not reach is the output this
    projection exists for, so it is never quietly empty.
    """
    completeness = Completeness()

    if report is not None:
        for reason in report.reasons():
            completeness = completeness.degraded(reason)

    if tombstone.at is None:
        return completeness.degraded(
            f"no erasure instant for {dataset} — nothing emitted a lifecycle event for it "
            "and no --since was given, so there is nothing to measure a rewrite against"
        )

    if not tombstone.evidenced:
        completeness = completeness.degraded(
            "the erasure instant came from --since rather than from an emitted lifecycle "
            "event, so every rewrite below is measured against a date somebody typed"
        )

    if not descendants:
        return completeness.degraded(
            f"nothing in the window read {dataset} — no descendants were found, which is "
            "not the same as the erased data having none"
        )

    unreached = [d for d in descendants if not d.reached]
    if unreached:
        n, total = len(unreached), len(descendants)
        completeness = completeness.degraded(
            f"{n} of {total} {plural(total, 'descendant', 'descendants')} "
            f"{plural(n, 'has', 'have')} not been rewritten since the tombstone: "
            f"{', '.join(d.dataset for d in unreached)}"
        )

    incomplete = [d for d in descendants if d.incomplete]
    if incomplete:
        n = len(incomplete)
        completeness = completeness.degraded(
            f"{n} {plural(n, 'descendant was', 'descendants were')} written by a run that "
            f"started after the tombstone and never reported completion — "
            f"{plural(n, 'it', 'they')} may or may not have been rewritten"
        )

    if scope.truncated:
        n = scope.truncated
        completeness = completeness.degraded(
            f"{n} {plural(n, 'branch', 'branches')} stopped at the depth limit of "
            f"{scope.depth_limit}, so anything derived further downstream was never looked at"
        )

    return completeness
