"""Every value in a record, explained in a sentence a reviewer can follow (#48).

An explanation says where a value came from, built only from facts the record
already holds — the job, the run whose event carried it, the mapping rule and
the line it is on, the declaration — and which requirement the field answers.
It names what it rests on, so a reader, or the console, can follow it there.

What it never does is judge. No *therefore lawful*, no *valid*, no *correct*:
whether a legal basis is the right one is a person's call (#41), and a sentence
that sounded like an answer would be the green shield in prose.
`tests/test_explain.py` holds every explanation to that, and to never saying
more than the provenance it is built from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .references import Reference, References
from .ropa import Provenance, Sourced

if TYPE_CHECKING:
    from .declared import Declared
    from .ropa import Activity

#: The words a field is called by in a sentence.
LABELS = {
    "purpose": "purpose",
    "legal_basis": "legal basis",
    "recipients": "recipients",
    "security_measures": "security measures",
}


@dataclass(frozen=True)
class Link:
    """Something an explanation rests on, for a reader to follow."""

    #: `run`, `rule` or `declaration`.
    kind: str
    #: The run id, the rule's pattern, or the declared activity's name.
    id: str
    file: str = ""
    line: int | None = None


@dataclass(frozen=True)
class Explanation:
    text: str
    answers: Reference | None
    rests_on: tuple[Link, ...] = ()


def _at(file: str, line: int | None) -> str:
    return f"{file} (line {line})" if line else file


def _vocabulary(sourced: Sourced, label: str, vocabulary: str) -> str:
    if not sourced.unrecognised:
        return ""
    return f" `{sourced.value}` is not a {label} the `{vocabulary}` vocabulary defines."


def _window(activity: Activity) -> str:
    n = activity.runs
    times = "once" if n == 1 else f"{n} times"
    if activity.first_seen and activity.last_seen:
        first, last = activity.first_seen.date(), activity.last_seen.date()
        when = f" on {first}" if first == last else f" between {first} and {last}"
    else:
        when = ""
    return f" The job ran {times} in the window{when}."


def activity_value(
    activity: Activity,
    field_name: str,
    sourced: Sourced,
    *,
    references: References,
    vocabulary: str,
) -> Explanation:
    """The purpose or the legal basis of a job that emitted lineage."""
    label = LABELS[field_name]
    job = activity.key
    answers = references.answers(field_name)
    tail = _vocabulary(sourced, label, vocabulary)

    if sourced.provenance is Provenance.FACET:
        run = f", on run `{sourced.run}`" if sourced.run else ""
        return Explanation(
            f"Emitted by `{job}` in its `processing` facet{run}.{_window(activity)}{tail}",
            answers,
            (Link("run", sourced.run),) if sourced.run else (),
        )

    if sourced.provenance is Provenance.MAPPING:
        return Explanation(
            f"Asserted in {_at(sourced.file, sourced.line)}, rule `{sourced.rule}`, because "
            f"`{job}` emitted no {label} in a `processing` facet.{tail}",
            answers,
            (Link("rule", sourced.rule, sourced.file, sourced.line),),
        )

    # Absent. Say which source was looked at and found silent, and nothing else.
    if activity.rule is not None:
        rule = activity.rule
        where = (
            f"the rule that matches it in {_at(activity.mapping, rule.line)}, "
            f"`{rule.pattern}`, sets none"
        )
        links: tuple[Link, ...] = (Link("rule", rule.pattern, activity.mapping, rule.line),)
    elif activity.mapping:
        where = f"no rule in {activity.mapping} matches it"
        links = ()
    else:
        where = "there is no mapping file"
        links = ()
    return Explanation(
        f"Nothing states a {label}: `{job}` emitted none in a `processing` facet, and {where}.",
        answers,
        links,
    )


def activity_list(
    activity: Activity, field_name: str, values: tuple[str, ...], *, references: References
) -> Explanation:
    """Recipients or security measures of a job: only ever from a mapping rule."""
    label = LABELS[field_name]
    job = activity.key
    answers = references.answers(field_name)
    rule = activity.rule
    if values and rule is not None:
        return Explanation(
            f"Asserted in {_at(activity.mapping, rule.line)}, rule `{rule.pattern}`. Lineage "
            f"carries no {label}, so they can only be asserted.",
            answers,
            (Link("rule", rule.pattern, activity.mapping, rule.line),),
        )
    if rule is not None:
        return Explanation(
            f"The rule that matches `{job}` in {_at(activity.mapping, rule.line)}, "
            f"`{rule.pattern}`, names no {label}.",
            answers,
            (Link("rule", rule.pattern, activity.mapping, rule.line),),
        )
    where = (
        f"no rule in {activity.mapping} matches it"
        if activity.mapping
        else "there is no mapping file"
    )
    return Explanation(
        f"Nothing names {label} for `{job}`: lineage carries none, and {where}.",
        answers,
    )


def declared_value(
    entry: Declared,
    field_name: str,
    sourced: Sourced,
    *,
    references: References,
    vocabulary: str,
) -> Explanation:
    """A field of processing that emits no lineage, as somebody declared it."""
    label = LABELS[field_name]
    answers = references.answers(field_name)
    link = (Link("declaration", entry.name, sourced.file, sourced.line),)
    where = _at(sourced.file, sourced.line) or "the activities file"
    if sourced.provenance is Provenance.DECLARED:
        return Explanation(
            f"Declared in {where} for `{entry.name}`, processing that emits no lineage; "
            f"nothing in the events shows it.{_vocabulary(sourced, label, vocabulary)}",
            answers,
            link,
        )
    return Explanation(f"{where} declares `{entry.name}` without a {label}.", answers, link)


def declared_list(
    entry: Declared, field_name: str, values: tuple[str, ...], *, references: References
) -> Explanation:
    label = LABELS[field_name]
    answers = references.answers(field_name)
    where = _at(entry.purpose.file, entry.purpose.line) or "the activities file"
    link = (Link("declaration", entry.name, entry.purpose.file, entry.purpose.line),)
    if values:
        return Explanation(f"Declared in {where} for `{entry.name}`.", answers, link)
    return Explanation(f"{where} declares `{entry.name}` without {label}.", answers, link)
