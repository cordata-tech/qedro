"""A hand-maintained register, read so it can be checked against the record.

The AI Readiness pillar refuses a parallel AI governance programme on the
grounds that its register drifts from the Art. 30 record within two quarters
(cordata-tech/platform#48). That is a claim, and a claim this tool can make
checkable: given an organisation's own register and the record Qedro generates,
report the fields that disagree. See cordata-tech/qedro#24.

**The shape is the declared-activities document with two more keys.** There is
already a document here for *processing stated rather than evidenced*, and a
register is that, less the two things a register has and a declaration does not:

- `job`, the pipeline an entry claims to describe, used for matching
- `owner`, who maintains the entry — which is most of what makes a register drift

**It is never merged into a record.** A declared activity is part of the record
and withholds the mark; a register is an outside claim being checked against one,
and merging the two would let a register assert itself into the document it is
being compared with. So this is read by `qedro diff`, never by `qedro ropa`.

Its own `KEYS` rather than a frozenset shared with `declared.py`: an unknown key
there is a typo until proven otherwise, and adding `owner` to a set nothing reads
would weaken a check that is doing real work.

**A spreadsheet is not read here, and the trigger for reading one is written
down** rather than left to feel: the first register somebody actually has that is
a CSV. What its columns mean is a different question from the one this answers,
and guessing at it now would produce the wrong shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import document
from .errors import ConfigError
from .ropa import Provenance

#: What an entry may say. Everything here is an assertion by whoever maintains
#: the register — that is what makes it a register rather than a record.
KEYS = frozenset(
    {
        "job",
        "owner",
        "purpose",
        "legal_basis",
        "domain",
        "model",
        "inputs",
        "note",
        "recipients",
        "security_measures",
    }
)

#: Fields compared one value at a time, and what each is called in the record.
#: The names are the record's, because a finding reads *the register says X, the
#: record says Y* about one field and not about two spellings of one.
SINGLE = (("purpose", "purpose"), ("legal_basis", "legal basis"), ("domain", "domain"))

#: Fields where a change is a member appearing or disappearing. `inputs` is
#: matched against the record's `reads`: a register says what an activity takes
#: in, and the record knows that as the datasets it read.
SETS = (("inputs", "reads"), ("recipients", "recipients"), ("security_measures", "security"))


def looks_like(raw: Mapping[str, Any]) -> bool:
    """Whether a parsed document is a register rather than a record.

    Decided on the top-level key rather than the file suffix, because a register
    may be written as JSON and a record always is — so the suffix says nothing
    and the document says it plainly.
    """
    return isinstance(raw.get("register"), Mapping)


def read(path: str | Path) -> dict[str, Any]:
    """The register document as entries keyed by what each one claims to be.

    Returns a mapping of key to the entry's raw fields plus its `owner` and the
    name it was written under, which is what a finding needs to name it.
    """
    origin = str(path)
    raw = document.read(Path(path))
    if raw is None:
        raise ConfigError(f"{origin} is empty")
    return parse(raw, origin=origin)


def parse(raw: Mapping[str, Any], *, origin: str) -> dict[str, Any]:
    entries = raw.get("register")
    if not isinstance(entries, Mapping) or not entries:
        raise ConfigError(f"{origin} has no `register:` mapping")

    out: dict[str, Any] = {}
    for name, spec in entries.items():
        if not isinstance(spec, Mapping):
            raise ConfigError(f"entry {name!r} in {origin} should be a mapping")
        unknown = sorted(set(spec) - KEYS)
        if unknown:
            raise ConfigError(
                f"entry {name!r} in {origin} has unknown keys {', '.join(unknown)}. "
                f"Allowed: {', '.join(sorted(KEYS))}"
            )
        # `job:` when the entry names the pipeline it describes, else the name it
        # was written under. Never anything cleverer: a register entry silently
        # matched to the wrong activity reports agreement where there is none,
        # which is worse than the unmatched pair because it is invisible.
        key = _text(spec.get("job")) or str(name)
        if key in out:
            raise ConfigError(
                f"{origin} has two entries for {key!r} — a register with two rows for one "
                "activity cannot be checked against a record that has one"
            )
        out[key] = {"name": str(name), **{k: spec.get(k) for k in KEYS if k in spec}}
    return out


def entry(key: str, fields: Mapping[str, Any], *, origin: str):
    """One register row as a comparable entry.

    Everything it says is `DECLARED`: a register is somebody's assertion, and the
    provenance is what lets a finding say which side of a disagreement rests on
    evidence and which on a spreadsheet.
    """
    from .compare import Entry, Value

    single = {label: Value(_text(fields.get(key_)), Provenance.DECLARED) for key_, label in SINGLE}
    if _text(fields.get("model")):
        single["model"] = Value(_text(fields.get("model")), Provenance.DECLARED)

    sets = {
        label: tuple(
            Value(item, Provenance.DECLARED)
            for item in _listed(fields.get(key_), name=key, origin=origin, field=key_)
        )
        for key_, label in SETS
    }
    return Entry(
        key=key,
        kind="register",
        single=single,
        sets=sets,
        owner=_text(fields.get("owner")),
        name=str(fields.get("name", key)),
    )


def _listed(raw: Any, *, name: str, origin: str, field: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw.strip(),) if raw.strip() else ()
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return tuple(item.strip() for item in raw if item.strip())
    raise ConfigError(f"`{field}` for entry {name!r} in {origin} should be a list of strings")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
