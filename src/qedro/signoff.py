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

**Each entry names the version it covers**, as the SHA-256 of the record's JSON with
the two parts that do not describe the processing left out: the `qedro` block, which
names the tool version that wrote it, and `signoff`, which is this. The same command
over the same events gives the same hash, so a sign-off still covers a record built
again from the same evidence, and stops covering it when anything the record states
has changed.

**No store.** The file is written where the record is, like `--out`; kept in Git, its
history is the audit trail, and the commit that added an entry is a second timestamp
nobody here controls. Whether records persist anywhere else is what #15 decides.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
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

#: Left out of the hash: what wrote the document, and the sign-off itself.
UNHASHED = ("qedro", "signoff")

FORMAT = 1


@dataclass(frozen=True)
class Entry:
    """One change of state, for one version of the record."""

    record_sha256: str
    state: str
    by: str
    at: datetime
    note: str = ""

    def describe(self) -> str:
        when = self.at.date().isoformat()
        said = f" — {self.note}" if self.note else ""
        if self.state == "for sign-off":
            return f"waiting for sign-off, requested by {self.by} on {when}{said}"
        if self.state == "draft":
            return f"returned to draft by {self.by} on {when}{said}"
        return f"{self.state} by {self.by} on {when}{said}"


@dataclass(frozen=True)
class SignOff:
    """Every entry in a sign-off file, oldest first."""

    entries: tuple[Entry, ...] = ()

    def for_version(self, digest: str) -> tuple[Entry, ...]:
        return tuple(e for e in self.entries if e.record_sha256 == digest)

    def state(self, digest: str) -> str:
        own = self.for_version(digest)
        return own[-1].state if own else "draft"

    def standing(self, digest: str) -> Standing:
        own = self.for_version(digest)
        earlier = tuple(e for e in self.entries if e.record_sha256 != digest)
        return Standing(
            state=own[-1].state if own else "draft",
            latest=own[-1] if own else None,
            approved=next((e for e in reversed(own) if e.state == "approved"), None),
            earlier=next(
                (e for e in reversed(earlier) if e.state in ("approved", "published")), None
            ),
        )


@dataclass(frozen=True)
class Standing:
    """Where one version of a record stands, as its renderers print it."""

    state: str
    latest: Entry | None = None
    approved: Entry | None = None
    #: The most recent approval of a *different* version, when this one has none:
    #: the record changed after somebody signed it.
    earlier: Entry | None = None

    def describe(self) -> str:
        if self.latest is not None and self.state != "draft":
            line = self.latest.describe()
            if self.state == "published" and self.approved is not None:
                line += f" (approved by {self.approved.by} on {self.approved.at.date()})"
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


def digest(payload: Mapping[str, Any]) -> str:
    """The SHA-256 of a record's JSON, without the parts that do not describe it."""
    kept = {k: v for k, v in payload.items() if k not in UNHASHED}
    canonical = json.dumps(kept, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sidecar(record: str | Path) -> Path:
    """`record.json` → `record.signoff.json`, beside it."""
    path = Path(record)
    stem = path.name.removesuffix(".json")
    return path.with_name(f"{stem}.signoff.json")


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
            )
            for e in raw["entries"]
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise UsageError(f"{path} is not a sign-off file qedro can read") from None
    if any(e.state not in STATES for e in entries):
        raise UsageError(f"{path} names a state that is not one of {', '.join(STATES)}")
    return SignOff(entries)


def sign(
    record: str | Path, *, state: str, by: str, at: datetime, note: str = ""
) -> tuple[Path, Entry]:
    """Add one entry to a record's sign-off file, after checking the step is allowed.

    Returns the file written and the entry added. Nothing already in the file is
    changed: an entry is only ever appended.
    """
    if state not in STATES:
        raise UsageError(f"{state!r} is not a sign-off state. Use one of: {', '.join(STATES)}")
    if not by.strip():
        raise UsageError("a sign-off needs a name — add --as 'Erika Mustermann'")
    version = digest(read_record(record))
    path = sidecar(record)
    current = load(path)
    now = current.state(version)
    if state not in NEXT[now]:
        allowed = " or ".join(NEXT[now])
        raise UsageError(
            f"this version of {Path(record).name} is {now}; from there it can go to {allowed}, "
            f"not {state}"
        )
    entry = Entry(record_sha256=version, state=state, by=by.strip(), at=at, note=note.strip())
    entries = [*current.entries, entry]
    path.write_text(
        json.dumps(
            {
                "qedro_signoff": FORMAT,
                "record": Path(record).name,
                "entries": [
                    {
                        "record_sha256": e.record_sha256,
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
    return load(signoff_path).standing(digest(payload))
