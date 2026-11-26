"""Why a change in a record happened, as far as the events and files show it (#49).

`qedro status --against` says what changed since a record was signed. A reviewer
re-approving it also needs the cause, and this module gives each change the one
the evidence in front of it supports:

- **emitted** — the first run in the fresh window whose job emitted the new
  value, with the commit its `sourceCodeLocation` names, where it names one;
- **mapping** — the rule in the mapping file that now supplies the value, with
  its file and line;
- **declared** — the declared activity that supplies it;
- **first run** — for an activity the record did not have, its first run in
  the window; for a dataset newly read or written, the first run that did so;
- **stopped** — the value is gone and nothing in the window supplies it, which
  is a finding about the window, not a cause;
- **unattributed** — with why: a kind of change this does not trace yet, or a
  cause outside what the events show.

Nothing is guessed. A first run in the window that already carries the new value
is said to be the window's first, since the change may be older than the window.
Reading is all this does: no Git history is read in this slice, and nothing is
written anywhere.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from . import compare
from .compare import Change
from .events import Event
from .provenance import _code
from .ropa import FACET, Activity, Provenance, Record

EMITTED = "emitted"
MAPPING = "mapping"
DECLARED = "declared"
FIRST_RUN = "first run"
STOPPED = "stopped"
UNATTRIBUTED = "unattributed"

#: The record's field labels and the processing facet's keys for them.
FACET_KEYS = {"purpose": "purpose", "legal basis": "legal_basis"}


@dataclass(frozen=True)
class Attribution:
    """The cause of one change, and the sentence that says it."""

    cause: str
    says: str
    run: str = ""
    when: datetime | None = None
    commit: str = ""
    repository: str = ""
    path: str = ""
    rule: str = ""
    file: str = ""
    line: int | None = None


def _day(when: datetime | None) -> str:
    return when.date().isoformat() if when else "a time it did not report"


def _ordered(events: Iterable[Event]) -> list[Event]:
    return sorted(events, key=lambda e: (e.event_time is None, e.event_time or datetime.min))


def _from_run(cause: str, what: str, event: Event, first_of_job: Event | None) -> Attribution:
    """A cause found in one run: the run, its date and its commit where it names one."""
    code = _code(event)
    run = event.run.run_id
    says = f"{what} by run {run[:8]} on {_day(event.event_time)}"
    if code.commit:
        where = "/".join(p for p in (code.repository, code.path) if p)
        says += f", at commit {code.commit[:12]}" + (f" of {where}" if where else "")
    else:
        says += "; the run names no commit"
    if first_of_job is not None and first_of_job.run.run_id == run:
        # The job's first run in the window already carries it, so the change may
        # be older than the window; said rather than presented as the moment.
        says += " — the job's first run in the window, so it may be older than the window"
    return Attribution(
        cause,
        says,
        run=run,
        when=event.event_time,
        commit=code.commit,
        repository=code.repository,
        path=code.path,
    )


def _rule(activity: Activity, what: str) -> Attribution | None:
    rule = activity.rule
    if rule is None:
        return None
    where = activity.mapping or "the mapping file"
    at = f" line {rule.line}" if rule.line else ""
    return Attribution(
        MAPPING,
        f"{what} the rule `{rule.pattern}` in {where}{at}",
        rule=rule.pattern,
        file=activity.mapping,
        line=rule.line,
    )


def _single(change: Change, activity: Activity | None, events: Sequence[Event]) -> Attribution:
    """A purpose or legal basis: emitted, mapped, declared, or stopped."""
    label = change.label
    after = change.after
    if after is None or activity is None:
        return Attribution(UNATTRIBUTED, "the fresh run does not have this activity")
    if after.provenance is Provenance.FACET:
        key = FACET_KEYS.get(label, "")
        for event in events:
            emitted = (event.job_facet(FACET) or {}).get(key)
            if isinstance(emitted, str) and emitted.strip() == after.value:
                return _from_run(EMITTED, f"first emitted as {after.value}", event, events[0])
        return Attribution(UNATTRIBUTED, "no run in the window shows it being emitted")
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


def _dataset(change: Change, events: Sequence[Event]) -> Attribution:
    """A dataset read or written: the first run that did, or none in the window."""
    side = "inputs" if change.field == "reads" else "outputs"
    verb = "read" if change.field == "reads" else "written"
    if change.kind == compare.GAINED and change.after is not None:
        key = change.after.value
        for event in events:
            if any(d.key == key for d in getattr(event, side)):
                return _from_run(FIRST_RUN, f"first {verb}", event, events[0])
        return Attribution(UNATTRIBUTED, f"no run in the window shows it being {verb}")
    return Attribution(STOPPED, f"no run in the window {verb} it")


def _listed_by_rule(change: Change, activity: Activity | None) -> Attribution:
    """Recipients, security measures and a mapped domain come from a rule or nowhere."""
    if activity is not None and change.kind != compare.LOST:
        found = _rule(activity, "listed by")
        if found is not None:
            return found
    if change.kind == compare.LOST:
        return Attribution(STOPPED, "no rule in the mapping file lists it any more")
    return Attribution(UNATTRIBUTED, "no rule in the mapping file is recorded for it")


def attribute(change: Change, activity: Activity | None, events: Sequence[Event]) -> Attribution:
    """The cause of one change to one activity, from its fresh activity and its events."""
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
        return _single(change, activity, events)
    if change.field in ("reads", "writes"):
        return _dataset(change, events)
    if change.field in ("recipients", "security measures", "domain"):
        return _listed_by_rule(change, activity)
    return Attribution(
        UNATTRIBUTED,
        "qedro does not trace this kind of change to its cause yet; a classification "
        "comes from a dataset's tags, read from any event that touched it",
    )


def added(change: Change, events: Sequence[Event]) -> Attribution:
    """An activity the signed record did not have: its first run in the window, or
    the activities document for one declared with no lineage."""
    if change.entry_kind == "declared":
        return Attribution(DECLARED, "added to the activities document, with no lineage behind it")
    if not events:
        return Attribution(UNATTRIBUTED, "no run of it is in the window")
    return _from_run(FIRST_RUN, "first ran", events[0], events[0])


class Attributor:
    """Attributes each change against one fresh run: its record and its events."""

    def __init__(self, record: Record, events: Iterable[Event]) -> None:
        self.activities: Mapping[str, Activity] = {a.key: a for a in record.activities}
        grouped: dict[str, list[Event]] = {}
        for event in events:
            grouped.setdefault(event.job.key, []).append(event)
        self.events: Mapping[str, list[Event]] = {k: _ordered(v) for k, v in grouped.items()}

    def change(self, change: Change) -> Attribution:
        return attribute(
            change, self.activities.get(change.entry), self.events.get(change.entry, [])
        )

    def new(self, change: Change) -> Attribution:
        return added(change, self.events.get(change.entry, []))


def attribution_json(attribution: Attribution) -> dict[str, object]:
    """A cause for `--format json`, beside the change it explains: the sentence and
    the evidence it rests on, with null where there is none."""
    return {
        "cause": attribution.cause,
        "says": attribution.says,
        "run": attribution.run or None,
        "when": attribution.when.isoformat() if attribution.when else None,
        "commit": attribution.commit or None,
        "repository": attribution.repository or None,
        "path": attribution.path or None,
        "rule": attribution.rule or None,
        "file": attribution.file or None,
        "line": attribution.line,
    }
