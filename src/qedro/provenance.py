"""The provenance projection.

Answers the question a published number provokes: *where did this come from,
and who authorised it?* Given a dataset, walk backwards — the run that produced
it, the code that run executed, the commit that code was at, whether that commit
was signed — and then do the same for everything that run read, and everything
those runs read, until the chain reaches data nothing in the window produced.

`quality` walks nothing; `ropa` groups by job. This is the only projection that
follows the graph, which is where its two failure modes come from.

**A chain that ends is not the same as a chain that is complete.** Walking
upstream stops for three different reasons — the dataset is a genuine source
that nothing produces, its producing run fell outside the window, or the depth
cap was reached. Those look identical in the output unless the output says
which, so each is counted separately and named.

**Absence of a signature is not absence of authorisation.** OpenLineage has a
standard place for the code identity — ``sourceCodeLocation``, carrying the
repository and the commit — and no standard place at all for whether that
commit was signed. So an unknown signature is reported as unknown and withholds
the mark; it is never rendered as unsigned. Saying *this ran under an unsigned
commit* when nobody reported either way would be inventing evidence, which is
the one thing this repository exists to argue against.

Nothing here reaches for a forge API to resolve a commit. Read-only is a
property of what the code can touch, and a projection that phoned GitHub would
have acquired a network dependency and a credential to go with it. Resolving
commits belongs to the integration the architecture notes place at v0.6, not to
a CLI that reads a directory.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from . import scope as scope_module
from .config import Config, Controller
from .events import Event
from .mark import Completeness
from .sources import ReadReport
from .words import count, plural

#: The standard OpenLineage job facet naming the code that ran. dbt, Airflow
#: and Spark all emit it, which is why the chain works without anything of ours.
CODE = "sourceCodeLocation"

#: Run facets asked, in order, whether the commit was signed. There is no
#: standard spelling for this — `sourceCodeLocation` stops at the commit — so
#: this is a short list of the ones that exist rather than a vocabulary. An
#: emitter using any of these keys is understood; anything else reports
#: unknown, which withholds the mark rather than guessing. Tracked in #5.
SIGNATURE_FACETS = ("cordata_provenance", "gitProvenance", "provenance")
SIGNATURE_KEYS = ("descriptor_git_commit_signed", "commit_signed", "signed")

#: How far upstream to walk before stopping. Deep enough for any real pipeline
#: graph, and bounded because a cycle in emitted lineage is not hypothetical.
#: Reaching it is stated in the output — a chain that stopped silently looks
#: like a chain that ended.
DEPTH = 10


@dataclass(frozen=True)
class Code:
    """Where the code that ran lived, as the emitter reported it."""

    repository: str = ""
    commit: str = ""
    branch: str = ""
    path: str = ""

    def __bool__(self) -> bool:
        return bool(self.commit or self.repository)

    @property
    def short(self) -> str:
        return self.commit[:12] if self.commit else ""

    def describe(self) -> str:
        if not self:
            return "no code location was emitted"
        where = self.repository or "an unnamed repository"
        at = f" at {self.short}" if self.commit else " at an unreported commit"
        return f"{where}{at}"


@dataclass(frozen=True)
class Signature:
    """Whether the commit was signed, including *nobody said*.

    Three states, and the third is the common one. `unknown` withholds the mark
    exactly as `False` does, because a chain that cannot show authorisation is
    not a chain that shows it — but the two are never rendered alike.
    """

    signed: bool | None = None
    reported_by: str = ""

    @property
    def known(self) -> bool:
        return self.signed is not None

    def describe(self) -> str:
        if self.signed is True:
            return f"signed (reported by {self.reported_by})"
        if self.signed is False:
            return f"not signed (reported by {self.reported_by})"
        return "signature unknown — nothing reported it"


@dataclass(frozen=True)
class Production:
    """One run that wrote one dataset."""

    job: str
    run_id: str
    event_type: str
    when: datetime | None
    code: Code
    signature: Signature
    reads: tuple[str, ...] = ()

    @property
    def authorised(self) -> bool:
        """Evidenced end to end: a commit, and a signature saying it held."""
        return bool(self.code.commit) and self.signature.signed is True


@dataclass(frozen=True)
class Step:
    """One dataset in the chain, and what produced it."""

    dataset: str
    depth: int
    production: Production | None = None
    #: Other runs that also wrote this dataset in the window. The chain follows
    #: the most recent; the count is reported so *the latest* never reads as
    #: *the only*.
    also_produced_by: int = 0
    #: Why the walk stopped here, if it did.
    ended: str = ""

    @property
    def known(self) -> bool:
        return self.production is not None


@dataclass(frozen=True)
class Scope(scope_module.Scope):
    """What the provenance run looked at."""

    dataset: str = ""
    steps: int = 0
    with_commit: int = 0
    with_signature: int = 0
    ends_unproduced: int = 0
    ends_at_depth: int = 0
    depth_limit: int = DEPTH

    OUT_OF_VIEW = (
        "This chain is built from lineage emitted inside the window. A step whose "
        "producing run ran before the window looks exactly like a source dataset that "
        "nothing produces, and neither is distinguishable here from a job that emits no "
        "lineage at all. The chain shows what was reported, not everything that happened."
    )

    def lines(self) -> tuple[tuple[str, str], ...]:
        out = [
            ("dataset", self.dataset or "unknown"),
            ("in view", f"{self.steps} steps, {self.events} events"),
            (
                "evidence",
                (
                    f"{self.with_commit} of {self.steps} steps name a commit, "
                    f"{self.with_signature} report a signature"
                ),
            ),
        ]
        ends = []
        if self.ends_unproduced:
            ends.append(f"{self.ends_unproduced} at datasets nothing in the window produced")
        if self.ends_at_depth:
            ends.append(f"{self.ends_at_depth} at the depth limit of {self.depth_limit}")
        if ends:
            out.append(("chain ends", "; ".join(ends)))
        return tuple(out)


@dataclass
class Record:
    """The chain from one dataset back to the commits that produced it."""

    controller: Controller
    dataset: str = ""
    steps: tuple[Step, ...] = ()
    scope: Scope = field(default_factory=Scope)
    completeness: Completeness = field(default_factory=Completeness)
    generated_from: str = ""

    @property
    def complete(self) -> bool:
        return self.completeness.complete

    @property
    def unauthorised(self) -> tuple[Step, ...]:
        """Steps that cannot show a signed commit, for whatever reason."""
        return tuple(s for s in self.steps if not (s.production and s.production.authorised))


def resolve(events: Iterable[Event], wanted: str) -> list[str]:
    """Dataset keys matching what the user typed.

    An exact `namespace/name` wins outright. Otherwise the bare name is matched,
    because nobody types the namespace and a tool that insisted would be
    tiresome — and every candidate is returned rather than one picked, so an
    ambiguous name is a question rather than a silently wrong answer.
    """
    keys = {d.key for e in events for d in e.datasets}
    if wanted in keys:
        return [wanted]
    return sorted(k for k in keys if k.rsplit("/", 1)[-1] == wanted)


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
    """Walk backwards from *dataset* through the runs that produced it."""
    events = list(events)
    producers: dict[str, list[Event]] = {}
    for event in events:
        for output in event.outputs:
            producers.setdefault(output.key, []).append(event)

    steps: list[Step] = []
    seen = {dataset}
    frontier = [(dataset, 0)]

    while frontier:
        key, level = frontier.pop(0)
        found = producers.get(key, [])
        if not found:
            steps.append(Step(dataset=key, depth=level, ended="nothing in the window produced it"))
            continue

        # The most recent run, with the rest counted rather than dropped.
        # Partitioned rather than sorted with a fallback key: two events with
        # no time at all would compare None against None and raise.
        timed = [e for e in found if e.event_time is not None]
        ordered = sorted(timed, key=lambda e: e.event_time, reverse=True) + [
            e for e in found if e.event_time is None
        ]
        production = _production(ordered[0])
        if level >= depth:
            steps.append(
                Step(
                    dataset=key,
                    depth=level,
                    production=production,
                    also_produced_by=len(ordered) - 1,
                    ended=f"the walk stopped at the depth limit of {depth}",
                )
            )
            continue

        steps.append(
            Step(
                dataset=key,
                depth=level,
                production=production,
                also_produced_by=len(ordered) - 1,
            )
        )
        for upstream in production.reads:
            if upstream not in seen:
                seen.add(upstream)
                frontier.append((upstream, level + 1))

    ordered_steps = tuple(sorted(steps, key=lambda s: (s.depth, s.dataset)))
    scope = _scope(
        ordered_steps,
        dataset=dataset,
        config=config,
        report=report,
        since=since,
        until=until,
        depth=depth,
    )

    return Record(
        controller=config.controller,
        dataset=dataset,
        steps=ordered_steps,
        scope=scope,
        completeness=_completeness(ordered_steps, dataset=dataset, scope=scope, report=report),
        generated_from=report.origin if report else "",
    )


def _production(event: Event) -> Production:
    return Production(
        job=event.job.key,
        run_id=event.run.run_id,
        event_type=event.event_type,
        when=event.event_time,
        code=_code(event),
        signature=_signature(event),
        reads=tuple(sorted({d.key for d in event.inputs})),
    )


def _code(event: Event) -> Code:
    facet = event.job_facet(CODE) or {}

    def text(*names: str) -> str:
        for name in names:
            value = facet.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    return Code(
        # `repoUrl` is the spec's spelling; `url` is what several emitters send.
        repository=text("repoUrl", "url"),
        commit=text("version"),
        branch=text("branch", "tag"),
        path=text("path"),
    )


def _signature(event: Event) -> Signature:
    """Whether the commit was signed, from whichever facet reported it."""
    for name in SIGNATURE_FACETS:
        facet = event.run_facet(name)
        if not facet:
            continue
        for key in SIGNATURE_KEYS:
            value = facet.get(key)
            if isinstance(value, bool):
                return Signature(signed=value, reported_by=name)
    return Signature()


def _scope(
    steps: Sequence[Step],
    *,
    dataset: str,
    config: Config,
    report: ReadReport | None,
    since: datetime | None,
    until: datetime | None,
    depth: int,
) -> Scope:
    times = [s.production.when for s in steps if s.production and s.production.when is not None]
    return Scope(
        source=report.origin if report else "",
        since=since if since is not None else (min(times) if times else None),
        until=until if until is not None else (max(times) if times else None),
        events=report.events if report else 0,
        # A chain is about one dataset and makes no claim about domain coverage,
        # so the declared domains are deliberately not carried into it. Passing
        # them through would report every domain as silent, which is a
        # different artefact's finding and would be false in this one.
        domains_declared=(),
        domains_seen=(),
        dataset=dataset,
        steps=len(steps),
        with_commit=sum(1 for s in steps if s.production and s.production.code.commit),
        with_signature=sum(1 for s in steps if s.production and s.production.signature.known),
        ends_unproduced=sum(1 for s in steps if s.ended and not s.production),
        ends_at_depth=sum(1 for s in steps if s.ended and s.production),
        depth_limit=depth,
    )


def _completeness(
    steps: Sequence[Step],
    *,
    dataset: str,
    scope: Scope,
    report: ReadReport | None,
) -> Completeness:
    """When a chain may claim to stand on its own evidence.

    The bar is high on purpose. *This number was produced by code at a signed
    commit* is the strongest claim any of the three projections makes, and it
    is only true when every step in the chain can show one.
    """
    completeness = Completeness()

    if report is not None:
        for reason in report.reasons():
            completeness = completeness.degraded(reason)

    produced = [s for s in steps if s.production]
    if not produced:
        return completeness.degraded(
            f"nothing in the window produced {dataset} — there is no chain to follow, "
            "which is not the same as the dataset having no origin"
        )

    missing_commit = [s for s in produced if not s.production.code.commit]  # type: ignore[union-attr]
    if missing_commit:
        n, total = len(missing_commit), len(produced)
        completeness = completeness.degraded(
            f"{n} of {total} {plural(total, 'step', 'steps')} emitted no code location, "
            f"so the code that produced {plural(n, 'it', 'them')} cannot be identified"
        )

    unsigned = [
        s
        for s in produced
        if s.production.signature.signed is False  # type: ignore[union-attr]
    ]
    if unsigned:
        completeness = completeness.degraded(
            f"{count(len(unsigned), 'step')} ran under a commit that was reported as not signed"
        )

    unknown = [
        s
        for s in produced
        if not s.production.signature.known  # type: ignore[union-attr]
    ]
    if unknown:
        n, total = len(unknown), len(produced)
        completeness = completeness.degraded(
            f"{n} of {total} {plural(total, 'step', 'steps')} "
            f"{plural(n, 'reports', 'report')} no signature either way — unknown is not "
            "the same as unsigned, and neither shows authorisation"
        )

    if scope.ends_unproduced:
        n = scope.ends_unproduced
        completeness = completeness.degraded(
            f"{n} {plural(n, 'branch', 'branches')} {plural(n, 'ends', 'end')} at "
            f"{plural(n, 'a dataset', 'datasets')} nothing in the window produced — "
            f"{plural(n, 'it may be a source', 'they may be sources')}, or the "
            "producing runs may be outside the window"
        )

    if scope.ends_at_depth:
        n = scope.ends_at_depth
        completeness = completeness.degraded(
            f"{n} {plural(n, 'branch', 'branches')} stopped at the depth limit of "
            f"{scope.depth_limit} rather than at {plural(n, 'its', 'their')} origin"
        )

    return completeness
