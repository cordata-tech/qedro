"""Whether a signed record still describes what runs (#42).

A signed record describes the platform on the day it was signed. Pipelines
change after that, and an outdated signed record reads exactly like a current
one. This compares each signed Art. 30 record with a fresh run over the same
source and gives every activity one of four states:

- **up to date** — the fresh run states the same values on the same evidence;
- **stale** — something the record states has changed, with what changed
  named, including a value that stayed the same while its evidence moved;
- **new** — an activity the fresh run has and the signed record does not;
- **blocked** — the comparison could not be made, always with the reason.

The comparison is `qedro diff`'s (#14), over the fields a record states and
never its run counts or timestamps, so a job that simply ran again is not
stale. File-based, as the sign-off is: a signed record and a fresh run are two
documents, and keeping a history of states is a store's job (#15).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import compare
from .attribution import Attribution, Attributor, attribution_json
from .compare import Change
from .errors import QedroError

UP_TO_DATE = "up to date"
STALE = "stale"
NEW = "new"
BLOCKED = "blocked"
#: In the order the summary counts them.
STATES: tuple[str, ...] = (UP_TO_DATE, STALE, NEW, BLOCKED)


@dataclass(frozen=True)
class ActivityState:
    key: str
    state: str
    #: What changed, for a stale activity: one finding per field, or the whole
    #: activity missing from the fresh run.
    changes: tuple[Change, ...] = ()
    #: Why each change happened, as far as the fresh run's events and files show
    #: it, in the order of `changes` (#49). Empty where nothing was attributed.
    causes: tuple[Attribution, ...] = ()
    #: For a new activity, its first run in the window or its declaration.
    cause: Attribution | None = None


@dataclass(frozen=True)
class RecordCheck:
    """One signed record against the fresh run."""

    origin: str
    activities: tuple[ActivityState, ...] = ()
    #: Why the comparison could not be made, when it could not. Every activity
    #: the record holds is then blocked, and this is printed, never only counted.
    blocked: str = ""
    #: How far apart the two are in ways that are reported rather than refused —
    #: a different window, a different source — from `qedro diff`.
    cautions: tuple[str, ...] = ()

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = dict.fromkeys(STATES, 0)
        for a in self.activities:
            out[a.state] += 1
        return out


def check(
    signed: dict[str, Any],
    fresh: dict[str, Any],
    *,
    origin: str,
    attributor: Attributor | None = None,
) -> RecordCheck:
    """One signed record, as JSON, against a fresh run's JSON.

    With an *attributor* — the fresh run's record and events — each change also
    gets its cause (#49). The comparison is the same either way.
    """
    try:
        before = compare.side(signed, origin=origin)
    except QedroError as exc:
        return RecordCheck(origin, blocked=str(exc))
    try:
        comparison = compare.compare(before, compare.side(fresh, origin="the fresh run"))
    except QedroError as exc:
        return blocked(origin, signed, str(exc))

    grouped = dict(comparison.by_entry())

    def causes(changes: tuple[Change, ...]) -> tuple[Attribution, ...]:
        return tuple(attributor.change(c) for c in changes) if attributor else ()

    states = [
        # Anything that differs is stale, including an activity the fresh run
        # does not have and a value whose evidence got stronger: either way the
        # signed record no longer says what runs.
        ActivityState(
            key,
            STALE if key in grouped else UP_TO_DATE,
            grouped.get(key, ()),
            causes(grouped.get(key, ())),
        )
        for key in sorted(before.entries)
    ]
    states += [
        ActivityState(c.entry, NEW, cause=attributor.new(c) if attributor else None)
        for c in comparison.changes
        if c.kind == compare.ADDED
    ]
    return RecordCheck(origin, tuple(states), cautions=comparison.comparability.cautions())


def blocked(origin: str, signed: dict[str, Any], reason: str) -> RecordCheck:
    """A record no fresh run could be compared with: each activity it holds is
    blocked, so the count says how much of the record is unchecked."""
    keys = [str(a.get("job", "")) for a in signed.get("activities") or ()]
    keys += [str(d.get("name", "")) for d in signed.get("declared") or ()]
    return RecordCheck(
        origin, tuple(ActivityState(k, BLOCKED) for k in sorted(keys)), blocked=reason
    )


def _value_json(value: compare.Value | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {"value": value.value, "provenance": str(value.provenance)}


def change_json(change: Change, cause: Attribution | None = None) -> dict[str, Any]:
    """One finding, with the words the text prints for it, so a reader such as
    the console says it as qedro does, and its cause where one was attributed."""
    from . import render

    if change.kind == compare.REMOVED:
        says, costs = "not in the fresh run", "it may not have run in the window"
    else:
        says, costs = render._finding(change)
    return {
        "field": change.label or None,
        "kind": change.kind,
        "before": _value_json(change.before),
        "after": _value_json(change.after),
        "says": says,
        "costs": costs or None,
        "cause": attribution_json(cause) if cause else None,
    }


def check_json(result: RecordCheck) -> dict[str, Any]:
    """A record's comparison with the fresh run, for `qedro status --format json`."""
    return {
        "blocked": result.blocked or None,
        "cautions": list(result.cautions),
        "counts": result.counts(),
        "activities": [
            {
                "key": a.key,
                "state": a.state,
                "changes": [
                    change_json(c, a.causes[i] if i < len(a.causes) else None)
                    for i, c in enumerate(a.changes)
                ],
                # Why a new activity is new: its first run, or its declaration.
                "cause": attribution_json(a.cause) if a.cause else None,
            }
            for a in result.activities
        ],
    }
