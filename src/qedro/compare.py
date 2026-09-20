"""What changed between two records — without a database.

`docs/architecture.md` argues that a blocked cloud migration, rather than the
compliance budget, may be what gets this tool adopted: legal will not approve
moving pipelines when nobody can show what processing exists today and what would
change. That before-and-after is a comparison of two records, and the
architecture puts it after a store. It does not need one. Two JSON documents a
team keeps in Git are enough, and building the comparison first tests whether the
migration case holds before a store is built for it. See cordata-tech/qedro#14.

**The finding this module exists for is invisible in either document alone.**
`purpose: fraud-detection` from an emitted facet and `purpose: fraud-detection`
from the mapping file are the same string and a different claim. A pipeline that
stopped emitting its facet still produces a record that reads correctly; what it
stopped producing is the evidence. `Provenance` is ordered, so a move down that
order is reported as a regression with the value unchanged.

**A comparison prints no mark of its own.** ∎ means *this artefact stands on its
own evidence*, and a comparison's evidence is two documents somebody handed it,
neither of which it can verify. It reports both records' verdicts instead — which
is also why a field that was wrong in both records is *unchanged* here, and
unchanged is not the same as right.

The entry model is deliberately not `Activity`. `quality` and `provenance`
records are comparable in the same way and are not built from activities, so what
this works over is an entry with an identity and fields that carry a value and a
provenance. Registering those two later is then a reader per projection rather
than a second comparison.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import ConfigError, UsageError
from .ropa import Provenance
from .scope import Scope

#: Document shapes this build can read. 0 is a document with no `qedro` block at
#: all, which is what 0.1 to 0.3 wrote — those are on PyPI and their output
#: exists, so they are read with the difference stated rather than refused.
KNOWN_SCHEMAS = frozenset({0, 1})

#: Projections that can be compared today. `quality` and `provenance` are the
#: same shape of problem and are not built yet (#14); refusing them by name is
#: what keeps that from being discovered as a wrong answer.
COMPARABLE = frozenset({"ropa"})

#: Worst-last, as `Provenance` declares them. A lower rank is stronger evidence.
RANK = {p: i for i, p in enumerate(Provenance)}

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"
REGRESSED = "regressed"
REPAIRED = "repaired"
GAINED = "gained"
LOST = "lost"


@dataclass(frozen=True)
class Value:
    """One value and what it rests on, which is the pair this tool never splits."""

    value: str
    provenance: Provenance = Provenance.ABSENT

    def __str__(self) -> str:
        return self.value or "nothing"


@dataclass(frozen=True)
class Entry:
    """One thing a record says happened, and what it says about it.

    `single` is fields with one value — a purpose, a lawful basis — where a
    change is *this became that*. `sets` is fields with several, where a change
    is a member appearing or disappearing and the rest staying put. Keeping them
    apart is what stops a reader being told that
    `[a, b]` changed to `[a, b, c]` without being told which one is new.
    """

    key: str
    kind: str
    single: dict[str, Value] = field(default_factory=dict)
    sets: dict[str, tuple[Value, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Change:
    """One finding. `field` is empty when the whole entry appeared or vanished."""

    entry: str
    kind: str
    entry_kind: str = "activity"
    field: str = ""
    before: Value | None = None
    after: Value | None = None

    @property
    def regression(self) -> bool:
        """Whether this finding is a loss of evidence rather than a change of fact.

        Provenance decides it, not the kind. A purpose that was emitted and is now
        absent arrives as `changed` — the value moved too — and is the worst of
        these findings rather than an ordinary one, so the rank is what is
        checked wherever both sides are present.
        """
        if self.kind in {REGRESSED, REMOVED, LOST}:
            return True
        if self.before is not None and self.after is not None:
            return RANK[self.after.provenance] > RANK[self.before.provenance]
        return False

    @property
    def label(self) -> str:
        """The field as a reader should see it, without its internal prefix."""
        return self.field.removeprefix("classification.")


@dataclass(frozen=True)
class Side:
    """One document, as far as a comparison is concerned."""

    origin: str
    schema: int
    projection: str
    view: str
    version: str
    source: str
    since: datetime | None
    until: datetime | None
    complete: bool
    reasons: tuple[str, ...]
    entries: dict[str, Entry]

    @property
    def shape(self) -> str:
        """What has to match on the other side for a comparison to mean anything."""
        return f"{self.projection}/{self.view}" if self.view else self.projection

    def window(self) -> str:
        if self.since is None and self.until is None:
            return "all events available from the source"
        start = self.since.isoformat() if self.since else "the earliest event available"
        end = self.until.isoformat() if self.until else "the latest event available"
        return f"{start} to {end}"


@dataclass(frozen=True)
class Comparability:
    """Whether the two documents cover the same ground, stated before any finding.

    A record over 30 days and a record over 7 can be compared, and the comparison
    is worth less. Saying so first is the difference between a reader weighing
    the findings and a reader believing processing changed when only the window
    did.
    """

    same_source: bool
    sources: tuple[str, str]
    overlap: str
    same_length: bool | None
    schemas: tuple[int, int]
    versions: tuple[str, str]

    @property
    def like_for_like(self) -> bool:
        return self.same_source and self.overlap == "identical"

    def cautions(self) -> tuple[str, ...]:
        """What a reader has to hold in mind while reading every finding below."""
        out = []
        if not self.same_source:
            out.append(
                f"the two records were read from different sources, "
                f"{self.sources[0]} and {self.sources[1]} — an activity missing from "
                "one may never have been in it"
            )
        if self.overlap == "disjoint":
            out.append(
                "the two windows do not overlap, so nothing here distinguishes "
                "processing that changed from processing that only ran at a "
                "different time"
            )
        elif self.overlap != "identical":
            out.append(
                f"the two windows are {self.overlap} rather than identical, so a "
                "difference in coverage can read as a difference in processing"
            )
        if self.same_length is False and self.overlap != "identical":
            out.append("the two windows are not the same length")
        if 0 in self.schemas:
            out.append(
                "one record was written before the document schema was numbered "
                "(qedro 0.3 or earlier), and is read on a best-effort basis"
            )
        return tuple(out)


@dataclass(frozen=True)
class CompareScope(Scope):
    """The comparison's own coverage statement.

    Its own standing sentence rather than the record's, because what a comparison
    cannot see is not what a record cannot see. See cordata-tech/qedro#3 for why
    this is printed unconditionally.

    The rows are computed once in `_scope` rather than from the two sides on
    every call: a scope is a statement about a run that has already happened, and
    holding the sides here only to re-derive four strings would make every
    renderer able to reach past the statement into the documents behind it.
    """

    rows: tuple[tuple[str, str], ...] = ()

    OUT_OF_VIEW = (
        "This comparison covers what the two documents report. It verifies neither — "
        "each was produced by a run against evidence that is not in front of it — so a "
        "field that was wrong in both records is reported here as unchanged, and "
        "unchanged is not the same as correct."
    )

    def lines(self) -> tuple[tuple[str, str], ...]:
        return self.rows


def _scope(before: Side, after: Side, comparability: Comparability) -> CompareScope:
    starts = [s for s in (before.since, after.since) if s is not None]
    ends = [s for s in (before.until, after.until) if s is not None]
    rows = [
        ("before", f"{before.origin} — {before.window()}"),
        ("after", f"{after.origin} — {after.window()}"),
        (
            "sources",
            comparability.sources[0]
            if comparability.same_source
            else " / ".join(comparability.sources),
        ),
        ("windows", comparability.overlap),
    ]
    if comparability.versions[0] != comparability.versions[1]:
        rows.append(
            ("written by", f"qedro {comparability.versions[0]} / qedro {comparability.versions[1]}")
        )
    return CompareScope(
        source=f"{before.origin} → {after.origin}",
        since=min(starts) if starts else None,
        until=max(ends) if ends else None,
        rows=tuple(rows),
    )


@dataclass(frozen=True)
class Comparison:
    """Two records, and what differs. Rendered like any other artefact."""

    before: Side
    after: Side
    comparability: Comparability
    changes: tuple[Change, ...]
    unchanged: int
    scope: CompareScope

    @property
    def regressions(self) -> tuple[Change, ...]:
        """Findings that are a loss of evidence rather than a change of fact."""
        return tuple(c for c in self.changes if c.regression)

    def by_entry(self) -> tuple[tuple[str, tuple[Change, ...]], ...]:
        """Findings grouped under the activity they are about, in reported order."""
        order: list[str] = []
        grouped: dict[str, list[Change]] = {}
        for change in self.changes:
            if change.entry not in grouped:
                grouped[change.entry] = []
                order.append(change.entry)
            grouped[change.entry].append(change)
        return tuple((key, tuple(grouped[key])) for key in order)


def read(path: str) -> Side:
    """One JSON document from disk, as a comparable side.

    What the user named is what raises: a file that is not JSON, or is JSON that
    is not one of this tool's documents, is a `ConfigError` with the path in it.
    Evidence is skipped and counted; a document somebody passed by name is not
    evidence.
    """
    text = Path(path).read_text(encoding="utf-8")
    try:
        raw = _json.loads(text)
    except _json.JSONDecodeError as error:
        raise ConfigError(f"{path} is not JSON: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} is JSON but not a qedro record")
    return side(raw, origin=path)


def side(raw: dict[str, Any], *, origin: str) -> Side:
    """A parsed document as a comparable side.

    A document with no `qedro` block is schema 0 and its projection has to be
    guessed from its keys — the one place this module guesses anything, and only
    because 0.1 to 0.3 shipped before the block existed.
    """
    document = raw.get("qedro")
    if isinstance(document, dict):
        schema = int(document.get("schema", 0))
        projection = str(document.get("projection", ""))
        view = str(document.get("view", ""))
        version = str(document.get("version", ""))
    else:
        schema, version = 0, ""
        projection, view = _guess_shape(raw, origin)

    scope = raw.get("scope")
    scope = scope if isinstance(scope, dict) else {}
    window = scope.get("window")
    window = window if isinstance(window, dict) else {}
    return Side(
        origin=origin,
        schema=schema,
        projection=projection,
        view=view,
        version=version,
        source=str(scope.get("source", "")),
        since=_instant(window.get("since")),
        until=_instant(window.get("until")),
        complete=bool(raw.get("complete", False)),
        reasons=tuple(raw.get("reasons") or ()),
        entries=_entries(raw),
    )


def _guess_shape(raw: dict[str, Any], origin: str) -> tuple[str, str]:
    """Which projection wrote a document from before the block existed."""
    if "activities" in raw:
        return "ropa", "deployer" if raw.get("view") == "deployer" else "art30"
    if "datasets" in raw:
        return "quality", ""
    if "steps" in raw:
        return "provenance", ""
    raise ConfigError(
        f"{origin} has no `qedro` block and does not look like a record this tool wrote"
    )


def _instant(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _entries(raw: dict[str, Any]) -> dict[str, Entry]:
    entries = {}
    for activity in raw.get("activities") or ():
        entry = _activity(activity)
        entries[entry.key] = entry
    for declared in raw.get("declared") or ():
        entry = _declared(declared)
        entries[entry.key] = entry
    return entries


def _sourced(raw: Any, default: Provenance = Provenance.ABSENT) -> Value:
    if not isinstance(raw, dict):
        return Value(str(raw or ""), default)
    return Value(str(raw.get("value", "")), _provenance(raw.get("provenance"), default))


def _provenance(raw: Any, default: Provenance = Provenance.ABSENT) -> Provenance:
    try:
        return Provenance(str(raw))
    except ValueError:
        return default


def _listed(raw: Any, provenance: Provenance) -> tuple[Value, ...]:
    """A list of plain strings that all rest on the same thing."""
    if isinstance(raw, dict):
        raw = raw.get("values")
    return tuple(Value(str(v), provenance) for v in (raw or ()))


def _activity(raw: dict[str, Any]) -> Entry:
    single = {
        "purpose": _sourced(raw.get("purpose")),
        "legal basis": _sourced(raw.get("legal_basis")),
        # The domain's provenance is which way it was decided, because a domain
        # that stopped being mapped and started being guessed is the same string
        # and a weaker claim. See #9.
        "domain": Value(
            str(raw.get("domain", "")),
            Provenance.MAPPING if raw.get("domain_source") == "mapping" else Provenance.ABSENT,
        ),
    }
    sets: dict[str, tuple[Value, ...]] = {
        "reads": _listed(raw.get("reads"), Provenance.FACET),
        "writes": _listed(raw.get("writes"), Provenance.FACET),
        "recipients": _listed(raw.get("recipients"), Provenance.MAPPING),
        "security measures": _listed(raw.get("security_measures"), Provenance.MAPPING),
    }
    # Classification is keyed by vocabulary term, prefixed so a term named
    # `reads` cannot collide with the dataset list. The vocabulary is a document
    # an organisation writes, so its terms are not a closed set.
    grouped: dict[str, list[Value]] = {}
    for item in raw.get("classification") or ():
        if not isinstance(item, dict):
            continue
        key = f"classification.{item.get('key', '')}"
        grouped.setdefault(key, []).append(
            Value(str(item.get("value", "")), _provenance(item.get("provenance")))
        )
    for key, values in grouped.items():
        sets[key] = tuple(sorted(values, key=lambda v: v.value))
    return Entry(key=str(raw.get("job", "")), kind="activity", single=single, sets=sets)


def _declared(raw: dict[str, Any]) -> Entry:
    return Entry(
        key=str(raw.get("name", "")),
        kind="declared",
        single={
            "purpose": _sourced(raw.get("purpose"), Provenance.DECLARED),
            "legal basis": _sourced(raw.get("legal_basis"), Provenance.DECLARED),
            "domain": Value(str(raw.get("domain", "")), Provenance.DECLARED),
            "model": Value(str(raw.get("model", "")), Provenance.DECLARED),
        },
        sets={
            "inputs": _listed(raw.get("inputs_declared"), Provenance.DECLARED),
            "recipients": _listed(raw.get("recipients"), Provenance.DECLARED),
            "security measures": _listed(raw.get("security_measures"), Provenance.DECLARED),
        },
    )


def _overlap(before: Side, after: Side) -> str:
    """How the two windows sit against each other.

    `unknown` when either side is open — a record over *everything available*
    has no window to compare, and saying so beats inventing one.
    """
    if None in (before.since, before.until, after.since, after.until):
        return "unknown"
    assert before.since and before.until and after.since and after.until
    if (before.since, before.until) == (after.since, after.until):
        return "identical"
    if before.until == after.since or after.until == before.since:
        return "adjacent"
    if before.since <= after.until and after.since <= before.until:
        return "overlapping"
    return "disjoint"


def _comparability(before: Side, after: Side) -> Comparability:
    lengths = [(s.until - s.since) if s.since and s.until else None for s in (before, after)]
    return Comparability(
        same_source=before.source == after.source,
        sources=(before.source or "unknown", after.source or "unknown"),
        overlap=_overlap(before, after),
        same_length=None if None in lengths else lengths[0] == lengths[1],
        schemas=(before.schema, after.schema),
        versions=(before.version or "unknown", after.version or "unknown"),
    )


def compare(before: Side, after: Side) -> Comparison:
    """Two sides, and what differs. The one refusal is a difference of shape.

    Everything else about how far apart the two records are — a different source,
    a different window, a different length of window — is reported rather than
    refused, because those comparisons are the ones a reader most often needs and
    the caution is what makes them safe.
    """
    if before.shape != after.shape:
        raise UsageError(
            f"these are different documents: {before.origin} is {before.shape} and "
            f"{after.origin} is {after.shape}. A comparison between them would have "
            "nothing to say that was true of either"
        )
    if before.projection not in COMPARABLE:
        raise UsageError(
            f"{before.projection or 'this'} records cannot be compared yet — only "
            "`ropa`. See cordata-tech/qedro#14"
        )
    for s in (before, after):
        if s.schema not in KNOWN_SCHEMAS:
            raise UsageError(
                f"{s.origin} is schema {s.schema}, which this build of qedro "
                f"({', '.join(str(k) for k in sorted(KNOWN_SCHEMAS))}) cannot read"
            )

    comparability = _comparability(before, after)
    changes, unchanged = _changes(before, after)
    return Comparison(
        before=before,
        after=after,
        comparability=comparability,
        changes=changes,
        unchanged=unchanged,
        scope=_scope(before, after, comparability),
    )


def _changes(before: Side, after: Side) -> tuple[tuple[Change, ...], int]:
    changes: list[Change] = []
    unchanged = 0
    for key in sorted(set(before.entries) | set(after.entries)):
        old, new = before.entries.get(key), after.entries.get(key)
        if old is None and new is not None:
            changes.append(Change(entry=key, kind=ADDED, entry_kind=new.kind))
            continue
        if new is None and old is not None:
            changes.append(Change(entry=key, kind=REMOVED, entry_kind=old.kind))
            continue
        assert old is not None and new is not None
        found = _entry_changes(old, new)
        changes.extend(found)
        if not found:
            unchanged += 1
    return tuple(changes), unchanged


def _entry_changes(old: Entry, new: Entry) -> list[Change]:
    out: list[Change] = []
    for name in sorted(set(old.single) | set(new.single)):
        before = old.single.get(name, Value(""))
        after = new.single.get(name, Value(""))
        if before == after:
            continue
        if before.value != after.value:
            kind = CHANGED
        else:
            # The same string, resting on something else. This is the finding no
            # single record can show, so it is named as a direction rather than
            # reported as a difference in a field a reader would skim past.
            kind = REGRESSED if RANK[after.provenance] > RANK[before.provenance] else REPAIRED
        out.append(
            Change(
                entry=old.key,
                kind=kind,
                entry_kind=old.kind,
                field=name,
                before=before,
                after=after,
            )
        )
    for name in sorted(set(old.sets) | set(new.sets)):
        was = {v.value: v for v in old.sets.get(name, ())}
        now = {v.value: v for v in new.sets.get(name, ())}
        for value in sorted(set(now) - set(was)):
            out.append(
                Change(
                    entry=old.key, kind=GAINED, entry_kind=old.kind, field=name, after=now[value]
                )
            )
        for value in sorted(set(was) - set(now)):
            out.append(
                Change(entry=old.key, kind=LOST, entry_kind=old.kind, field=name, before=was[value])
            )
        for value in sorted(set(was) & set(now)):
            if was[value].provenance == now[value].provenance:
                continue
            kind = (
                REGRESSED if RANK[now[value].provenance] > RANK[was[value].provenance] else REPAIRED
            )
            out.append(
                Change(
                    entry=old.key,
                    kind=kind,
                    entry_kind=old.kind,
                    field=name,
                    before=was[value],
                    after=now[value],
                )
            )
    return out
