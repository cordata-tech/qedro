"""Why a change in a record happened, as far as the events and files show it (#49).

`qedro status --against` says what changed in a signed record; a reviewer
re-approving it also needs the cause. The fresh run usually reads the whole
source, events from before the signing included, so the end of the signed
record's window is a boundary: what each job did up to it, and what it did after.
Each change gets the cause the evidence in front of qedro supports:

- **emitted** — the first run after the boundary that emitted the new value, with
  its commit, and the commit the job ran at before;
- **mapping** — the rule now supplying the value, with its file and line, and,
  where the mapping file is in Git, the commit that last changed that line;
- **declared** — a declared activity, whose document no event can date;
- **tagged** — for a classification, the run whose event first tagged the
  dataset with the new value, and the job that emitted it;
- **first run** — a new activity, or a dataset newly read or written, with, for a
  dataset read, the chain of jobs that produce it, each one before → after the
  boundary: its commit, and the inputs it gained or lost;
- **stopped** — a value gone with nothing supplying it, which is a finding about
  the window rather than a cause;
- **unattributed** — with the reason.

Nothing is guessed. Where a job has no run before the boundary in the events, the
cause says the change may be older than what the events show. Reading only: the
events, the mapping file, and its Git history through `history`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from . import compare, history
from .compare import Change
from .events import Event
from .provenance import _code
from .ropa import FACET, Activity, Provenance, Record

EMITTED = "emitted"
MAPPING = "mapping"
DECLARED = "declared"
TAGGED = "tagged"
FIRST_RUN = "first run"
STOPPED = "stopped"
UNATTRIBUTED = "unattributed"

#: The record's field labels and the processing facet's keys for them.
FACET_KEYS = {"purpose": "purpose", "legal basis": "legal_basis"}

#: How far up the provenance chain a newly read dataset is followed, in jobs. A
#: chain longer than this is cut and says so, rather than growing without bound.
MAX_STEPS = 8


@dataclass(frozen=True)
class Step:
    """One level of the provenance chain above a newly read dataset: the job that
    writes it, before and after the boundary."""

    dataset: str
    job: str
    #: Whether the job has no run before the boundary in the events.
    new: bool
    commit_before: str = ""
    commit_after: str = ""
    inputs_gained: tuple[str, ...] = ()
    inputs_lost: tuple[str, ...] = ()
    run: str = ""
    when: datetime | None = None

    @property
    def changed(self) -> bool:
        return bool(
            self.new
            or self.inputs_gained
            or self.inputs_lost
            or (
                self.commit_before and self.commit_after and self.commit_before != self.commit_after
            )
        )

    def says(self) -> str:
        text = f"{self.dataset} is written by {self.job}"
        if self.new:
            return text + ", which has no run before the sign-off in the events"
        parts = []
        if self.commit_before and self.commit_after and self.commit_before != self.commit_after:
            parts.append(f"commit {self.commit_before[:12]} → {self.commit_after[:12]}")
        if self.inputs_gained:
            parts.append(f"now also reading {', '.join(self.inputs_gained)}")
        if self.inputs_lost:
            parts.append(f"no longer reading {', '.join(self.inputs_lost)}")
        return text + (f" ({'; '.join(parts)})" if parts else ", unchanged since the sign-off")


@dataclass(frozen=True)
class Attribution:
    """The cause of one change, and the sentence that says it."""

    cause: str
    says: str
    run: str = ""
    when: datetime | None = None
    commit: str = ""
    #: The commit the job ran at before the boundary, where it differs.
    commit_before: str = ""
    repository: str = ""
    path: str = ""
    job: str = ""
    rule: str = ""
    file: str = ""
    line: int | None = None
    #: The commit that last changed the rule's line, from Git, or why not.
    rule_change: history.LineChange | None = None
    history: str = ""
    #: The jobs above a newly read dataset, nearest first.
    upstream: tuple[Step, ...] = field(default_factory=tuple)


def _day(when: datetime | None) -> str:
    return when.date().isoformat() if when else "a time it did not report"


def _ordered(events: Iterable[Event]) -> list[Event]:
    return sorted(events, key=lambda e: (e.event_time is None, e.event_time or datetime.min))


def _where(event: Event) -> tuple[str, str]:
    code = _code(event)
    where = "/".join(p for p in (code.repository, code.path) if p)
    return code.commit, where


class Context:
    """One fresh run's events, split at the boundary where the signed record ends."""

    def __init__(self, events: Iterable[Event], boundary: datetime | None) -> None:
        self.boundary = boundary
        by_job: dict[str, list[Event]] = {}
        writers: dict[str, list[Event]] = {}
        for event in events:
            by_job.setdefault(event.job.key, []).append(event)
            for d in event.outputs:
                writers.setdefault(d.key, []).append(event)
        self.by_job = {k: _ordered(v) for k, v in by_job.items()}
        self.writers = {k: _ordered(v) for k, v in writers.items()}
        self.every = _ordered(e for v in by_job.values() for e in v)

    def before(self, events: Sequence[Event]) -> list[Event]:
        if self.boundary is None:
            return []
        return [e for e in events if e.event_time is not None and e.event_time <= self.boundary]

    def after(self, events: Sequence[Event]) -> list[Event]:
        if self.boundary is None:
            return list(events)
        return [e for e in events if e.event_time is None or e.event_time > self.boundary]


def _from_run(
    cause: str, what: str, event: Event, ctx: Context, upstream: tuple[Step, ...] = ()
) -> Attribution:
    """A cause found in one run: the run, its date, its commit, and the run before."""
    commit, where = _where(event)
    run, job = event.run.run_id, event.job.key
    says = f"{what} by run {run[:8]} on {_day(event.event_time)}"
    says += (
        (f", at commit {commit[:12]}" + (f" of {where}" if where else ""))
        if commit
        else ("; the run names no commit")
    )
    earlier = ctx.before(ctx.by_job.get(job, []))
    commit_before = ""
    if earlier:
        last = earlier[-1]
        commit_before, _ = _where(last)
        says += f"; the job's last run before the sign-off, {last.run.run_id[:8]} on {_day(last.event_time)}"
        if commit_before and commit and commit_before != commit:
            says += f", ran at commit {commit_before[:12]}"
        elif commit_before and commit_before == commit:
            says += ", ran at the same commit"
    else:
        # Nothing of this job before the boundary in the events: the change may
        # be older than they show, which is said rather than presented as the moment.
        says += "; the job has no run before the sign-off in the events, so it may be older"
    if upstream:
        says += "; upstream: " + "; ".join(s.says() for s in upstream)
        if len(upstream) >= MAX_STEPS:
            says += f"; the chain is cut at {MAX_STEPS} jobs"
    return Attribution(
        cause,
        says,
        run=run,
        when=event.event_time,
        commit=commit,
        commit_before=commit_before if commit_before != commit else "",
        repository=_code(event).repository,
        path=_code(event).path,
        job=job,
        upstream=upstream,
    )


def _rule(activity: Activity, what: str) -> Attribution | None:
    rule = activity.rule
    if rule is None:
        return None
    where = activity.mapping or "the mapping file"
    at = f" line {rule.line}" if rule.line else ""
    says = f"{what} the rule `{rule.pattern}` in {where}{at}"
    changed: history.LineChange | None = None
    reason = ""
    if activity.mapping and rule.line:
        # The rule's whole block, pattern and the fields under it: a changed
        # purpose sits on a line of its own below the pattern.
        found = history.line_change(
            activity.mapping, rule.line, history.block_end(activity.mapping, rule.line)
        )
        if isinstance(found, history.LineChange):
            changed = found
            says += (
                f", last changed in commit {found.commit[:12]} by {found.author} "
                f"on {found.when[:10]}: {found.subject}"
            )
        else:
            reason = found.reason
            says += f"; its history is not available: {reason}"
    return Attribution(
        MAPPING,
        says,
        rule=rule.pattern,
        file=activity.mapping,
        line=rule.line,
        rule_change=changed,
        history=reason,
    )


def _single(change: Change, activity: Activity | None, ctx: Context) -> Attribution:
    """A purpose or legal basis: emitted, mapped, declared, or stopped."""
    label = change.label
    after = change.after
    if after is None or activity is None:
        return Attribution(UNATTRIBUTED, "the fresh run does not have this activity")
    if after.provenance is Provenance.FACET:
        key = FACET_KEYS.get(label, "")
        for event in ctx.after(ctx.by_job.get(change.entry, [])):
            emitted = (event.job_facet(FACET) or {}).get(key)
            if isinstance(emitted, str) and emitted.strip() == after.value:
                return _from_run(EMITTED, f"first emitted as {after.value}", event, ctx)
        return Attribution(UNATTRIBUTED, "no run after the sign-off shows it being emitted")
    if after.provenance is Provenance.MAPPING:
        before = change.before
        lead = (
            f"no run in the window emitted a {label}; now supplied by"
            if before is not None and before.provenance is Provenance.FACET
            else "supplied by"
        )
        return _rule(activity, lead) or Attribution(
            UNATTRIBUTED, "it comes from the mapping file, and no rule is recorded for it"
        )
    if after.provenance is Provenance.DECLARED:
        return Attribution(DECLARED, "supplied by a declared activity, with no lineage behind it")
    return Attribution(
        STOPPED,
        f"no run in the window emitted a {label} and no rule supplies one; "
        "what stopped it is not in the events",
    )


def _upstream(dataset: str, ctx: Context) -> tuple[Step, ...]:
    """The jobs above *dataset*, nearest first, followed where something changed.

    At each level, the job that writes the dataset after the boundary, compared
    with itself before it: its commit, and the inputs it read. The walk goes on
    into the inputs that are new at that level — all of them for a job new since
    the sign-off — and stops where nothing changed, at a dataset nothing in the
    events writes, or at `MAX_STEPS`.
    """
    steps: list[Step] = []
    seen: set[str] = set()
    pending = [dataset]
    while pending and len(steps) < MAX_STEPS:
        current = pending.pop(0)
        if current in seen:
            continue
        seen.add(current)
        written = ctx.after(ctx.writers.get(current, []))
        if not written:
            continue
        first = written[0]
        job = first.job.key
        runs = ctx.by_job.get(job, [])
        before, after = ctx.before(runs), ctx.after(runs)
        read_before = {d.key for e in before for d in e.inputs}
        read_after = {d.key for e in after for d in e.inputs}
        commit_after, _ = _where(after[0]) if after else ("", "")
        commit_before, _ = _where(before[-1]) if before else ("", "")
        step = Step(
            dataset=current,
            job=job,
            new=not before,
            commit_before=commit_before,
            commit_after=commit_after,
            inputs_gained=tuple(sorted(read_after - read_before)) if before else (),
            inputs_lost=tuple(sorted(read_before - read_after)) if before else (),
            run=first.run.run_id,
            when=first.event_time,
        )
        steps.append(step)
        # Up through what changed at this level; a job new since the sign-off
        # changed as a whole, so all it reads is followed.
        pending.extend(sorted(read_after) if step.new else step.inputs_gained)
    return tuple(steps)


def _dataset(change: Change, ctx: Context) -> Attribution:
    """A dataset read or written: the first run that did after the sign-off, and for
    one read, the provenance chain above it before → after."""
    side = "inputs" if change.field == "reads" else "outputs"
    verb = "read" if change.field == "reads" else "written"
    if change.kind == compare.GAINED and change.after is not None:
        key = change.after.value
        for event in ctx.after(ctx.by_job.get(change.entry, [])):
            if any(d.key == key for d in getattr(event, side)):
                upstream = _upstream(key, ctx) if side == "inputs" else ()
                return _from_run(FIRST_RUN, f"first {verb}", event, ctx, upstream)
        return Attribution(UNATTRIBUTED, f"no run after the sign-off shows it being {verb}")
    return Attribution(STOPPED, f"no run in the window {verb} it")


def _tags(event: Event, dataset: str) -> set[tuple[str, str]]:
    """The (key, value) tags an event's `tags` dataset facet puts on *dataset*."""
    out: set[tuple[str, str]] = set()
    for d in (*event.inputs, *event.outputs):
        if d.key != dataset:
            continue
        for item in (d.facets.get("tags") or {}).get("tags") or ():
            if isinstance(item, dict) and isinstance(item.get("key"), str):
                out.add((item["key"], str(item.get("value", ""))))
    return out


def _classification(change: Change, activity: Activity | None, ctx: Context) -> Attribution:
    """A classification value gained: the run whose event first tagged a dataset the
    activity touches with it, whichever job emitted that event."""
    if change.kind == compare.LOST:
        return Attribution(
            STOPPED, "no event in the window tags a dataset this activity touches with it"
        )
    if activity is None or change.after is None:
        return Attribution(UNATTRIBUTED, "the fresh run does not have this activity")
    key, value = change.label, change.after.value
    datasets = {
        d
        for c in activity.classification
        if c.key == key and c.value == value
        for d in (*c.reads, *c.writes)
    }
    for event in ctx.after(ctx.every):
        for dataset in sorted(datasets):
            if (key, value) in _tags(event, dataset):
                found = _from_run(TAGGED, f"first tagged {key} {value} on {dataset}", event, ctx)
                job = event.job.key
                if job != change.entry:
                    return replace(found, says=found.says + f"; the event is {job}'s")
                return found
    return Attribution(
        UNATTRIBUTED,
        "no event after the sign-off tags it; it may come from a catalog qedro reads "
        "rather than from the events",
    )


def _listed_by_rule(change: Change, activity: Activity | None) -> Attribution:
    """Recipients, security measures and a mapped domain come from a rule or nowhere."""
    if activity is not None and change.kind != compare.LOST:
        found = _rule(activity, "listed by")
        if found is not None:
            return found
    if change.kind == compare.LOST:
        return Attribution(STOPPED, "no rule in the mapping file lists it any more")
    return Attribution(UNATTRIBUTED, "no rule in the mapping file is recorded for it")


def attribute(change: Change, activity: Activity | None, ctx: Context) -> Attribution:
    """The cause of one change to one activity, from its fresh activity and the events."""
    if change.entry_kind == "declared":
        # Processing with no lineage: the activities document is the only source,
        # so its edit is the cause, and nothing in the events can say when.
        return Attribution(
            DECLARED,
            "a declared activity: the activities document says this now, "
            "and no event can show when it changed",
        )
    if change.kind == compare.REMOVED:
        return Attribution(STOPPED, "no run of this job is in the window")
    if change.field in FACET_KEYS:
        return _single(change, activity, ctx)
    if change.field in ("reads", "writes"):
        return _dataset(change, ctx)
    if change.field in ("recipients", "security measures", "domain"):
        return _listed_by_rule(change, activity)
    if change.field.startswith("classification."):
        return _classification(change, activity, ctx)
    return Attribution(UNATTRIBUTED, "qedro does not trace this kind of change to its cause yet")


def added(change: Change, ctx: Context) -> Attribution:
    """An activity the signed record did not have: its first run after the sign-off,
    or the activities document for one declared with no lineage."""
    if change.entry_kind == "declared":
        return Attribution(DECLARED, "added to the activities document, with no lineage behind it")
    runs = ctx.after(ctx.by_job.get(change.entry, []))
    if not runs:
        return Attribution(UNATTRIBUTED, "no run of it is in the window")
    return _from_run(FIRST_RUN, "first ran", runs[0], ctx)


class Attributor:
    """Attributes each change against one fresh run: its record and its events."""

    def __init__(
        self, record: Record, events: Iterable[Event], boundary: datetime | None = None
    ) -> None:
        self.record = record
        self.events = list(events)
        self.activities: Mapping[str, Activity] = {a.key: a for a in record.activities}
        self.ctx = Context(self.events, boundary)

    def at(self, boundary: datetime | None) -> Attributor:
        """The same fresh run, split where a signed record's window ends."""
        return Attributor(self.record, self.events, boundary)

    def change(self, change: Change) -> Attribution:
        return attribute(change, self.activities.get(change.entry), self.ctx)

    def new(self, change: Change) -> Attribution:
        return added(change, self.ctx)


def _step_json(step: Step) -> dict[str, object]:
    return {
        "dataset": step.dataset,
        "job": step.job,
        "new": step.new,
        "commit": {"before": step.commit_before or None, "after": step.commit_after or None},
        "inputs": {"gained": list(step.inputs_gained), "lost": list(step.inputs_lost)},
        "run": step.run or None,
        "when": step.when.isoformat() if step.when else None,
    }


def attribution_json(attribution: Attribution) -> dict[str, object]:
    """A cause for `--format json`, beside the change it explains: the sentence and
    the evidence it rests on, with null where there is none."""
    change = attribution.rule_change
    return {
        "cause": attribution.cause,
        "says": attribution.says,
        "run": attribution.run or None,
        "when": attribution.when.isoformat() if attribution.when else None,
        "job": attribution.job or None,
        "commit": attribution.commit or None,
        "commit_before": attribution.commit_before or None,
        "repository": attribution.repository or None,
        "path": attribution.path or None,
        "rule": attribution.rule or None,
        "file": attribution.file or None,
        "line": attribution.line,
        "rule_change": (
            {
                "commit": change.commit,
                "when": change.when,
                "author": change.author,
                "subject": change.subject,
            }
            if change
            else None
        ),
        "history": attribution.history or None,
        "upstream": [_step_json(s) for s in attribution.upstream],
    }
