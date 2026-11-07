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
#: `provenance`, and for the same reason: a closure over a real platform can be
#: large, and a truncated list that does not say it was truncated is the failure
#: this repository cares most about.
DEPTH = 5

#: The lifecycle states that are an erasure. `ALTER`, `CREATE` and `RENAME` are
#: the other three the standard facet defines, and a rename is not a deletion —
#: mistaking one for the other would report a proof that never happened.
ERASURES = frozenset({"DROP", "TRUNCATE", "OVERWRITE"})

#: The two that remove everything. An `OVERWRITE` replaces the contents, and
#: Spark reports one on every overwriting write, so it says the table was
#: rewritten rather than that anything was erased. It can still anchor the
#: tombstone, but a drop or truncate is preferred over it, and several of them
#: with nothing to choose between withhold the mark. See cordata-tech/qedro#29.
REMOVALS = frozenset({"DROP", "TRUNCATE"})

#: How an output says a run replaced its contents rather than adding to them
#: (#35). A lifecycle state of the three that remove or replace, from any
#: emitter; or dbt's materialisation, which `openlineage-dbt` sends on each
#: output as the `dbt_model` facet. `table` and `view` replace what was there;
#: `incremental` and `snapshot` keep it, so a run of either adds to a dataset
#: without touching what it held before the erasure. dbt reports no
#: `--full-refresh` in its events, so a full refresh of an incremental model is
#: read as an append — the direction that withholds the mark, never the one
#: that grants it. Anything else does not say how it wrote.
REBUILDS = frozenset({"DROP", "TRUNCATE", "OVERWRITE"})
DBT_REBUILDS = frozenset({"table", "view"})
DBT_APPENDS = frozenset({"incremental", "snapshot"})

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
    #: Completed runs that dropped, truncated or overwrote the dataset and could
    #: have been the erasure: all of them in the window, or those from `--since`
    #: on. More than one is reported, since which was taken is then a choice.
    candidates: int = 0
    #: The lifecycle states among those candidates, for saying what they did.
    candidate_states: frozenset[str] = frozenset()
    #: Whether `--since` picked the candidate, as the first at or after it.
    #: Otherwise the latest was taken, which on a table overwritten nightly is
    #: last night's run rather than the erasure.
    chosen_by_since: bool = False

    @property
    def evidenced(self) -> bool:
        return self.provenance is Provenance.FACET

    @property
    def ambiguous(self) -> bool:
        """Several overwrites, and nothing to say which one was the erasure."""
        return (
            self.evidenced
            and self.state not in REMOVALS
            and self.candidates > 1
            and not self.chosen_by_since
        )

    def describe(self) -> str:
        if self.at is None:
            return "no erasure instant"
        if self.evidenced and self.state in REMOVALS:
            return f"{self.at.isoformat()} — emitted {self.state.lower()}"
        if self.evidenced:
            # Not called the erasure: the event says the table was replaced.
            return f"{self.at.isoformat()} — emitted overwrite, not a drop or truncate"
        return f"{self.at.isoformat()} — from --since, not emitted"

    def earned(self) -> str:
        """The sentence a record that earns the mark ends on.

        Names what the event reported rather than calling it an erasure: the mark
        is earned only on an emitted tombstone, and when that was an overwrite the
        line above already says it was not a drop or truncate, so the verdict
        calling it *an emitted erasure* contradicted it.
        """
        return f"every descendant was written after the emitted {self.state.lower()}"

    def choice(self) -> str:
        """Which candidate was taken and why, or "" when there was only one."""
        if self.candidates < 2:
            return ""
        verbs = {"DROP": "dropped", "TRUNCATE": "truncated", "OVERWRITE": "overwrote"}
        did = [verbs[s] for s in ("DROP", "TRUNCATE", "OVERWRITE") if s in self.candidate_states]
        done = did[0] if len(did) == 1 else f"{', '.join(did[:-1])} or {did[-1]}"
        taken = (
            "the first after --since was taken"
            if self.chosen_by_since
            else "the latest was taken, as no --since says when the erasure was requested"
        )
        preferred = (
            ", a drop or truncate in preference to an overwrite"
            if self.state in REMOVALS and "OVERWRITE" in self.candidate_states
            else ""
        )
        return f"{self.candidates} completed runs {done} it; {taken}{preferred}"


@dataclass(frozen=True)
class Descendant:
    """One dataset derived from the erased one, and what happened to it since."""

    dataset: str
    depth: int
    #: The job whose run derived it from upstream. Named so a reader who has to
    #: go and rewrite this dataset knows what to run.
    through: str = ""
    #: The most recent completed run that wrote it after the tombstone, of any kind.
    written: datetime | None = None
    #: The most recent of those whose output said it replaced the contents.
    rebuilt: datetime | None = None
    runs_since: int = 0
    #: Completed runs since the tombstone that said they appended, and those
    #: that did not say how they wrote. See `REBUILDS` and #35.
    appends: int = 0
    unreported: int = 0
    #: Runs that started after the tombstone and never reported completion. Not
    #: the same as not written, and not the same as written.
    incomplete: int = 0
    truncated: bool = False

    @property
    def how(self) -> str:
        """`rebuilt`, `written` (how not reported), `appended`, or "" when nothing wrote it.

        The strongest evidence among the runs since the tombstone decides it: one
        rebuild is enough, and a run that did not say how it wrote might have
        been one, so only a descendant every run of which appended is
        `appended`.
        """
        if self.rebuilt is not None:
            return "rebuilt"
        if self.unreported:
            return "written"
        if self.appends:
            return "appended"
        return ""

    @property
    def reached(self) -> bool:
        """Whether the erasure demonstrably propagated this far.

        A rebuild, or a write that did not say how — as before #35, under wording
        that no longer claims the contents were replaced. Not an append: what
        the dataset held before the erasure is still in it.
        """
        return self.how in ("rebuilt", "written")


@dataclass(frozen=True)
class Scope(scope_module.Scope):
    """What the erasure run looked at, and what it could never have looked at."""

    dataset: str = ""
    descendants: int = 0
    rebuilt: int = 0
    written: int = 0
    appended: int = 0
    not_written: int = 0
    incomplete: int = 0
    truncated: int = 0
    depth_limit: int = DEPTH
    tombstone: Tombstone = field(default_factory=lambda: Tombstone(dataset=""))

    OUT_OF_VIEW = (
        "This record covers datasets, not rows. It can show that a dataset descends "
        "from the erased one and that a job wrote it after the erasure; it cannot "
        "show that a particular data subject's rows are gone, because no lineage event "
        "carries that. A write replaced a dataset's contents only where the event says "
        "so — an overwrite, truncate or drop, or a dbt table or view — and an "
        "appending job adds to a dataset without touching what it held before, so a "
        "descendant only appended to since the erasure is not counted as reached. A "
        "write that did not say how is counted, and the record says it did not say: "
        "evidence that the erasure was propagated, not proof that it was complete."
    )

    def lines(self) -> tuple[tuple[str, str], ...]:
        out = [
            ("erased", self.dataset or "unknown"),
            ("tombstone", self.tombstone.describe()),
            ("in view", f"{count(self.descendants, 'descendant')}, {self.events} events"),
        ]
        if self.tombstone.choice():
            out.append(("candidates", self.tombstone.choice()))
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
        parts = [
            f"{n} {label}"
            for n, label in (
                (self.rebuilt, "rebuilt"),
                (self.written, "written without saying how"),
                (self.appended, "only appended to"),
                (self.not_written, "not written"),
            )
            if n
        ]
        reached = f"of {count(self.descendants, 'descendant')}: {', '.join(parts)}"
        out.append(("propagation", f"{reached} since the tombstone" if parts else reached))
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

    A candidate is a **run** whose events name the dataset as an output with a
    `lifecycleStateChange` of `DROP`, `TRUNCATE` or `OVERWRITE`, and which
    reported completion; its instant is the completion. Counted per run because
    Spark carries the facet on every event of one write, and only completed runs
    because a drop that failed erased nothing.

    Which candidate is the erasure (cordata-tech/qedro#29):

    - With `--since`, the first at or after it: the operator has said when the
      erasure was requested, and the first removal after that is the one that
      could have carried it out. Without it, the latest, as before.
    - A drop or truncate is preferred over an overwrite. Spark reports an
      overwrite on every overwriting write, so on a table rewritten nightly the
      latest overwrite is last night's run rather than the erasure.
    """
    runs: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.event_time is None:
            continue
        # Naive is UTC, the one assumption `sources` already makes. Refusing to
        # compare would be worse, and inventing a second rule here worse still.
        when = utc(event.event_time)
        run = runs.setdefault(
            event.run.run_id or f"{event.job.key}@{when.isoformat()}",
            {"states": set(), "completed": None},
        )
        if event.event_type == "COMPLETE":
            run["completed"] = when
        for output in event.outputs:
            if output.key == dataset and (state := _lifecycle(output)) in ERASURES:
                run["states"].add(state)

    # A run reporting more than one state is taken at its strongest.
    strongest = ("DROP", "TRUNCATE", "OVERWRITE")
    candidates = [
        (run["completed"], next(s for s in strongest if s in run["states"]))
        for run in runs.values()
        if run["states"] and run["completed"] is not None
    ]
    if since is not None:
        candidates = [c for c in candidates if c[0] >= utc(since)]

    if candidates:
        removals = [c for c in candidates if c[1] in REMOVALS]
        pool = removals or candidates
        at, state = (
            min(pool, key=lambda c: c[0]) if since is not None else max(pool, key=lambda c: c[0])
        )
        # `since` is kept rather than dropped, so the record can say the two
        # disagree instead of quietly preferring one.
        superseded = utc(since) if since is not None and utc(since) != at else None
        return Tombstone(
            dataset=dataset,
            at=at,
            provenance=Provenance.FACET,
            state=state,
            asserted_at=superseded,
            candidates=len(candidates),
            candidate_states=frozenset(s for _, s in candidates),
            chosen_by_since=since is not None,
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


def _how_written(output: Any) -> str:
    """`rebuilt`, `appended`, or "" when the output does not say. See `REBUILDS`."""
    if _lifecycle(output) in REBUILDS:
        return "rebuilt"
    model = output.facets.get("dbt_model")
    config = model.get("config") if isinstance(model, dict) else None
    materialized = config.get("materialized") if isinstance(config, dict) else None
    if materialized in DBT_REBUILDS:
        return "rebuilt"
    if materialized in DBT_APPENDS:
        return "appended"
    return ""


def _measure(descendant: Descendant, events: Sequence[Event], tombstone: Tombstone) -> Descendant:
    """Whether anything wrote this dataset after the erasure, and how.

    A completed run that wrote it counts; a run that started and never reported
    completion is counted apart, because *it may have finished* is not evidence
    and reporting it as a write would be inventing the proof. How a run wrote is
    read from any of its events, since an emitter may put the facet on START and
    not on COMPLETE; one that says it rebuilt the dataset outranks one that says
    it appended (#35).
    """
    if tombstone.at is None:
        return descendant

    completed: dict[str, datetime] = {}
    kinds: dict[str, set[str]] = {}
    started: set[str] = set()
    for event in events:
        if event.event_time is None:
            continue
        when = utc(event.event_time)
        if when <= tombstone.at:
            continue
        output = next((o for o in event.outputs if o.key == descendant.dataset), None)
        if output is None:
            continue
        run = event.run.run_id or f"{event.job.key}@{when.isoformat()}"
        kinds.setdefault(run, set()).add(_how_written(output))
        if event.event_type == "COMPLETE":
            completed[run] = max(when, completed.get(run, when))
        else:
            started.add(run)

    how = {
        run: "rebuilt"
        if "rebuilt" in kinds[run]
        else "appended"
        if "appended" in kinds[run]
        else ""
        for run in completed
    }
    rebuilds = [completed[run] for run in completed if how[run] == "rebuilt"]
    return Descendant(
        dataset=descendant.dataset,
        depth=descendant.depth,
        through=descendant.through,
        written=max(completed.values(), default=None),
        rebuilt=max(rebuilds, default=None),
        runs_since=len(completed),
        appends=sum(1 for run in completed if how[run] == "appended"),
        unreported=sum(1 for run in completed if how[run] == ""),
        incomplete=len(started - completed.keys()),
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
        passed_over=report.passed_over if report else (),
        since=since,
        until=until,
        events=report.events if report else 0,
        dataset=dataset,
        descendants=len(descendants),
        rebuilt=sum(1 for d in descendants if d.how == "rebuilt"),
        written=sum(1 for d in descendants if d.how == "written"),
        appended=sum(1 for d in descendants if d.how == "appended"),
        not_written=sum(1 for d in descendants if d.how == ""),
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

    Six ways it cannot, and each names something a reader would have to go and
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
            "and no --since was given, so there is nothing to measure a write against"
        )

    if tombstone.ambiguous:
        completeness = completeness.degraded(
            f"{tombstone.candidates} runs overwrote {dataset} in the window and nothing says "
            "which one carried out the erasure, so the latest was taken — on a table "
            "rewritten on a schedule that is the last scheduled run; pass --since with "
            "the date the erasure was requested"
        )

    if not tombstone.evidenced:
        completeness = completeness.degraded(
            "the erasure instant came from --since rather than from an emitted lifecycle "
            "event, so every write below is measured against a date somebody typed"
        )

    if not descendants:
        return completeness.degraded(
            f"nothing in the window read {dataset} — no descendants were found, which is "
            "not the same as the erased data having none"
        )

    total = len(descendants)
    unwritten = [d for d in descendants if d.how == ""]
    if unwritten:
        n = len(unwritten)
        completeness = completeness.degraded(
            f"{n} of {total} {plural(total, 'descendant', 'descendants')} "
            f"{plural(n, 'has', 'have')} not been written since the tombstone: "
            f"{', '.join(d.dataset for d in unwritten)}"
        )

    appended = [d for d in descendants if d.how == "appended"]
    if appended:
        n = len(appended)
        completeness = completeness.degraded(
            f"{n} of {total} {plural(total, 'descendant was', 'descendants were')} only "
            f"appended to since the tombstone, so what {plural(n, 'it', 'they')} held "
            f"before the erasure is still there: {', '.join(d.dataset for d in appended)}"
        )

    incomplete = [d for d in descendants if d.incomplete]
    if incomplete:
        n = len(incomplete)
        completeness = completeness.degraded(
            f"{n} {plural(n, 'descendant was', 'descendants were')} written by a run that "
            f"started after the tombstone and never reported completion — "
            f"{plural(n, 'it', 'they')} may or may not have been written"
        )

    if scope.truncated:
        n = scope.truncated
        completeness = completeness.degraded(
            f"{n} {plural(n, 'branch', 'branches')} stopped at the depth limit of "
            f"{scope.depth_limit}, so anything derived further downstream was never looked at"
        )

    return completeness
