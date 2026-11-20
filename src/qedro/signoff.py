"""A person's sign-off on a record, kept beside it (#40).

A record of processing activities is the controller's document, and a person signs
it. Qedro produces the record; this module keeps who accepted which version of it,
and when, in a small file beside the record's JSON:

    record.json            what `qedro ropa … --out record.json` wrote
    record.signoff.json    every sign-off entry for it, added to and never edited

**A sign-off is not evidence.** The mark says a record stands on what the pipelines
emitted; a sign-off says a person accepted the record, which is a different claim
made by somebody else. Nothing here reads or changes `complete` or the reasons, and
every renderer prints the sign-off beside the verdict, never in place of it.

**Each entry names what it covers**, as the SHA-256 of the record's *statements*:
the fields a person vouches for by approving it — the controller, each activity's
purpose and legal basis, its categories and recipients, what it reads and writes,
the verdict and its reasons — and nothing else. Run counts, timestamps, the window
and the tool version change every time a record is built again over new lineage,
and display fields such as a platform label say nothing about the processing;
hashing them would reopen every approval each night and at every upgrade, and a
signature that reopens for no reason teaches people to sign without reading.

The covered fields are an **explicit list per projection**, `COVERED`, not a list of
exclusions, so a field qedro adds later is outside the hash until somebody decides
it belongs in it. The list has a version, `COVERAGE`, recorded in every entry, and
an entry is always checked against the list it was made with: an upgrade never
reopens an approval by accident. When a release grows the list, the approval still
stands for what it covered, and the standing says that signing again would cover
more. Version 1, used by 0.16.0, hashed the whole record.

**No store.** The file is written where the record is, like `--out`; kept in Git, its
history is the audit trail, and the commit that added an entry is a second timestamp
nobody here controls. Whether records persist anywhere else is what #15 decides.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import UsageError

#: The states, in order. `draft` is where every version of a record starts.
STATES = ("draft", "for sign-off", "approved", "published")

#: Where each state may go next: one step forward, or back to draft.
NEXT: Mapping[str, tuple[str, ...]] = {
    "draft": ("for sign-off",),
    "for sign-off": ("approved", "draft"),
    "approved": ("published", "draft"),
    "published": ("draft",),
}

FORMAT = 1

#: The coverage new entries are made under. Raise it whenever `COVERED` changes.
COVERAGE = 2

Path_ = tuple[str, ...]

_VERDICT: tuple[Path_, ...] = (("complete",), ("reasons",))

#: What a sign-off vouches for, per kind of document: paths into its JSON, `*`
#: for every element of a list. Everything not named here is outside the hash.
COVERED: Mapping[str, tuple[Path_, ...]] = {
    "ropa/art30": (
        ("controller",),
        ("activities", "*", "job"),
        ("activities", "*", "domain"),
        ("activities", "*", "purpose"),
        ("activities", "*", "legal_basis"),
        ("activities", "*", "classification", "*", "key"),
        ("activities", "*", "classification", "*", "value"),
        ("activities", "*", "classification", "*", "provenance"),
        ("activities", "*", "classification", "*", "unrecognised"),
        ("activities", "*", "unclassified"),
        ("activities", "*", "recipients"),
        ("activities", "*", "security_measures"),
        ("activities", "*", "reads"),
        ("activities", "*", "writes"),
        ("declared",),
        *_VERDICT,
    ),
    "ropa/deployer": (
        ("controller",),
        ("references", "regulation"),
        ("use_cases", "*", "job"),
        ("use_cases", "*", "evidence"),
        ("use_cases", "*", "purpose"),
        ("use_cases", "*", "legal_basis"),
        ("use_cases", "*", "model_versions", "*", "version"),
        ("declared",),
        *_VERDICT,
    ),
    "erasure": (
        ("dataset",),
        ("tombstone", "at"),
        ("tombstone", "provenance"),
        ("tombstone", "lifecycle_state"),
        ("descendants", "*", "dataset"),
        ("descendants", "*", "derived_from"),
        ("descendants", "*", "derived_by"),
        ("descendants", "*", "how"),
        ("descendants", "*", "reached"),
        *_VERDICT,
    ),
    "provenance": (
        ("dataset",),
        ("steps", "*", "dataset"),
        ("steps", "*", "ended"),
        ("steps", "*", "production", "job"),
        ("steps", "*", "production", "code", "repository"),
        ("steps", "*", "production", "code", "commit"),
        ("steps", "*", "production", "signed"),
        ("steps", "*", "production", "authorised"),
        ("steps", "*", "production", "source_published"),
        *_VERDICT,
    ),
    "quality": (
        ("datasets", "*", "dataset"),
        ("datasets", "*", "holds"),
        ("datasets", "*", "expectations", "*", "assertion"),
        ("datasets", "*", "expectations", "*", "column"),
        ("datasets", "*", "expectations", "*", "holds"),
        ("unchecked",),
        *_VERDICT,
    ),
}


@dataclass(frozen=True)
class Entry:
    """One change of state, for one version of the record."""

    record_sha256: str
    state: str
    by: str
    at: datetime
    note: str = ""
    #: The `COVERED` version the hash was made under; 1 hashed the whole record.
    coverage: int = 1

    def describe(self, aside: str = "") -> str:
        """One line for this entry; *aside* goes after the date and before the note."""
        when = self.at.date().isoformat()
        said = f" — {self.note}" if self.note else ""
        if self.state == "for sign-off":
            return f"waiting for sign-off, requested by {self.by} on {when}{said}"
        if self.state == "draft":
            return f"returned to draft by {self.by} on {when}{said}"
        return f"{self.state} by {self.by} on {when}{aside}{said}"

    def covers(self, payload: Mapping[str, Any]) -> bool:
        return self.record_sha256 == digest(payload, coverage=self.coverage)


@dataclass(frozen=True)
class SignOff:
    """Every entry in a sign-off file, oldest first."""

    entries: tuple[Entry, ...] = ()

    def for_record(self, payload: Mapping[str, Any]) -> tuple[Entry, ...]:
        """The entries that cover this record, each checked under its own coverage."""
        return tuple(e for e in self.entries if e.covers(payload))

    def state(self, payload: Mapping[str, Any]) -> str:
        own = self.for_record(payload)
        return own[-1].state if own else "draft"

    def standing(self, payload: Mapping[str, Any]) -> Standing:
        own = self.for_record(payload)
        earlier = tuple(e for e in self.entries if e not in own)
        latest = own[-1] if own else None
        approved = next((e for e in reversed(own) if e.state == "approved"), None)
        return Standing(
            state=latest.state if latest else "draft",
            latest=latest,
            approved=approved,
            prepared=preparer(own, before=approved),
            earlier=next(
                (e for e in reversed(earlier) if e.state in ("approved", "published")), None
            ),
            narrower=latest is not None and latest.state != "draft" and latest.coverage < COVERAGE,
        )


def preparer(own: Sequence[Entry], *, before: Entry | None = None) -> Entry | None:
    """Who sent this version for sign-off: the last *for sign-off* entry before
    *before*, or the last one of all when nothing has been approved yet (#47)."""
    end = own.index(before) if before is not None and before in own else len(own)
    return next((e for e in reversed(own[:end]) if e.state == "for sign-off"), None)


def same_person(a: str, b: str) -> bool:
    """Whether two typed names are one person's, ignoring case and spacing. Typed,
    not authenticated: this catches a mistake, not a lie."""
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


@dataclass(frozen=True)
class Standing:
    """Where one version of a record stands, as its renderers print it."""

    state: str
    latest: Entry | None = None
    approved: Entry | None = None
    #: The most recent approval of a *different* version, when this one has none:
    #: the record changed after somebody signed it.
    earlier: Entry | None = None
    #: The approval stands, made when a sign-off covered less of the record than
    #: this qedro's does; signing again would cover the rest.
    narrower: bool = False
    #: Who sent this version for sign-off, the preparer, beside its approver (#47).
    prepared: Entry | None = None

    @property
    def second_person(self) -> bool | None:
        """Whether a different person approved this version than prepared it, or
        `None` while nothing is approved. Compared as typed with `--as`."""
        if self.approved is None or self.prepared is None:
            return None
        return not same_person(self.approved.by, self.prepared.by)

    def _four_eyes(self) -> str:
        if self.second_person is None:
            return ""
        assert self.prepared is not None
        if self.second_person:
            return f", prepared by {self.prepared.by} on {self.prepared.at.date()}"
        return f", with no second person: {self.prepared.by} also prepared it"

    def describe(self) -> str:
        if self.latest is not None and self.state != "draft":
            line = self.latest.describe(self._four_eyes() if self.state == "approved" else "")
            if self.state == "published" and self.approved is not None:
                line += (
                    f" (approved by {self.approved.by} on {self.approved.at.date()}"
                    f"{self._four_eyes()})"
                )
            if self.narrower:
                line += (
                    " — signed when a sign-off covered less of the record than this "
                    "version of qedro states; sign again to cover the rest"
                )
            return line
        if self.earlier is not None:
            return (
                "not signed off — the sign-off on file covers an earlier version of this "
                f"record, {self.earlier.describe()}"
            )
        if self.latest is not None:
            return f"not signed off — {self.latest.describe()}"
        return "not signed off"

    #: Said once beside every sign-off, so a signature is never read as evidence.
    CAVEAT = "a person's acceptance of the record, not evidence; it does not change the verdict"


def kind(payload: Mapping[str, Any]) -> str:
    """`ropa/art30`, `erasure`, …: which list of covered fields applies."""
    block = payload.get("qedro", {})
    projection = str(block.get("projection", ""))
    view = block.get("view")
    return f"{projection}/{view}" if view else projection


def statements(payload: Mapping[str, Any]) -> Any:
    """The part of a record a sign-off covers: its `COVERED` fields, nothing else."""
    paths = COVERED.get(kind(payload))
    if paths is None:
        raise UsageError(
            f"qedro cannot sign a {kind(payload) or 'document of no known kind'}: "
            f"it signs {', '.join(sorted(COVERED))}"
        )
    return _select(payload, paths)


def _select(value: Any, paths: Sequence[Path_]) -> Any:
    """*value* reduced to *paths*, keeping the shape and the order of lists."""
    if any(len(p) == 0 for p in paths):
        return value
    if isinstance(value, list):
        rest = [p[1:] for p in paths if p[0] == "*"]
        return [_select(item, rest) for item in value]
    if isinstance(value, Mapping):
        out = {}
        for key in dict.fromkeys(p[0] for p in paths):
            if key in value:
                out[key] = _select(value[key], [p[1:] for p in paths if p[0] == key])
        return out
    return value


def digest(payload: Mapping[str, Any], *, coverage: int = COVERAGE) -> str:
    """The SHA-256 of what a sign-off made under *coverage* vouches for."""
    if coverage == 1:
        # 0.16.0: the whole record but what wrote it and the sign-off itself.
        kept: Any = {k: v for k, v in payload.items() if k not in ("qedro", "signoff")}
    elif coverage == COVERAGE:
        kept = statements(payload)
    else:
        raise UsageError(f"a sign-off made under coverage {coverage} needs a newer qedro")
    canonical = json.dumps(kept, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: The suffix of a regenerated record waiting for sign-off beside the signed one
#: (#55). It shares that record's sign-off file, so one file holds the history
#: of every version and replacing the record with it after approval loses none.
NEXT_SUFFIX = ".next.json"


def _stem(record: str | Path) -> str:
    name = Path(record).name
    return (
        name.removesuffix(NEXT_SUFFIX) if name.endswith(NEXT_SUFFIX) else name.removesuffix(".json")
    )


def sidecar(record: str | Path) -> Path:
    """`record.json` → `record.signoff.json`, beside it; `record.next.json` too."""
    return Path(record).with_name(f"{_stem(record)}.signoff.json")


def next_version(record: str | Path) -> Path:
    """Where a regenerated version of *record* is written: `record.next.json`."""
    return Path(record).with_name(f"{_stem(record)}{NEXT_SUFFIX}")


def read_record(path: str | Path) -> Mapping[str, Any]:
    """A record's JSON, refused in a sentence when it is not one qedro wrote."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UsageError(f"no record at {path}") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise UsageError(
            f"{path} is not JSON — sign the record qedro wrote with --out record.json"
        ) from None
    if not (isinstance(payload, dict) and isinstance(payload.get("qedro"), dict)):
        raise UsageError(f"{path} is not a record qedro wrote: it has no `qedro` block")
    return payload


def load(path: str | Path) -> SignOff:
    """A sign-off file, or an empty sign-off when there is none yet."""
    path = Path(path)
    if not path.exists():
        return SignOff()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = tuple(
            Entry(
                record_sha256=e["record_sha256"],
                state=e["state"],
                by=e["by"],
                at=datetime.fromisoformat(e["at"]),
                note=e.get("note", ""),
                coverage=int(e.get("coverage", 1)),
            )
            for e in raw["entries"]
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise UsageError(f"{path} is not a sign-off file qedro can read") from None
    if any(e.state not in STATES for e in entries):
        raise UsageError(f"{path} names a state that is not one of {', '.join(STATES)}")
    return SignOff(entries)


def sign(
    record: str | Path,
    *,
    state: str,
    by: str,
    at: datetime,
    note: str = "",
    four_eyes: bool = True,
) -> tuple[Path, Entry]:
    """Add one entry to a record's sign-off file, after checking the step is allowed.

    With *four_eyes*, the default (#47), the person who sent a version for
    sign-off cannot approve it; `signoff: {four_eyes: false}` in qedro.yaml is
    for a team where one person does both, and the sign-off then says so.

    Returns the file written and the entry added. Nothing already in the file is
    changed: an entry is only ever appended.
    """
    if state not in STATES:
        raise UsageError(f"{state!r} is not a sign-off state. Use one of: {', '.join(STATES)}")
    if not by.strip():
        raise UsageError("a sign-off needs a name — add --as 'Erika Mustermann'")
    payload = read_record(record)
    path = sidecar(record)
    current = load(path)
    now = current.state(payload)
    if state not in NEXT[now]:
        allowed = " or ".join(NEXT[now])
        raise UsageError(
            f"this version of {Path(record).name} is {now}; from there it can go to {allowed}, "
            f"not {state}"
        )
    if state == "approved" and four_eyes:
        prepared = preparer(current.for_record(payload))
        if prepared is not None and same_person(prepared.by, by):
            raise UsageError(
                f"{by.strip()} sent this version of {Path(record).name} for sign-off, so "
                f"cannot approve it too: four eyes asks for a second person. Have someone "
                f"else approve it, or set `signoff: {{four_eyes: false}}` in qedro.yaml where "
                f"one person does both."
            )
    entry = Entry(
        record_sha256=digest(payload),
        state=state,
        by=by.strip(),
        at=at,
        note=note.strip(),
        coverage=COVERAGE,
    )
    entries = [*current.entries, entry]
    path.write_text(
        json.dumps(
            {
                "qedro_signoff": FORMAT,
                # The record the file belongs to, also when the entry is for its
                # regenerated version: one file, one record.
                "record": f"{_stem(record)}.json",
                "entries": [
                    {
                        "record_sha256": e.record_sha256,
                        "coverage": e.coverage,
                        "state": e.state,
                        "by": e.by,
                        "at": e.at.isoformat(),
                        **({"note": e.note} if e.note else {}),
                    }
                    for e in entries
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path, entry


def standing_of(payload: Mapping[str, Any], signoff_path: str | Path) -> Standing:
    """Where the record in *payload* stands against a sign-off file."""
    return load(signoff_path).standing(payload)
