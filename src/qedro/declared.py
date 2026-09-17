"""Declared activities: processing that emits no lineage, stated rather than invisible.

A controller writes these in their own document, passed with `--activities`, for
processing the events will never show — staff pasting tickets into a vendor's
assistant, an HR tool, anything on paper. They exist so that a record can say
*this happens* about processing it has no evidence for, and **every field here is
an assertion**: nothing in the events shows the activity happened, which model it
used, or what it read. Renderers mark each entry as declared, and any declared
entry withholds the mark. See cordata-tech/qedro#6.

Kept in a document of their own rather than in `qedro.yaml`, which is one of the
options #6 left open. A list of every non-pipeline use in an organisation is kept
by different people from a mapping rule and may be long, and keeping it separate
means an existing config is untouched until someone opts in.

Both views read it. In the Art. 30 record declared activities sit in their own
tuple beside the evidenced ones, are counted apart in the scope statement, and
withhold the mark; the deployer view lists those that name a `model`. The
reasoning for each of those is recorded on #6.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import document
from .errors import ConfigError
from .ropa import Provenance, Sourced
from .vocabulary import Vocabulary

#: What an entry may say. An unknown key is a typo until proven otherwise, and a
#: typo in a document that asserts a lawful basis is the kind that matters.
KEYS = frozenset({"purpose", "legal_basis", "domain", "model", "inputs", "note"})


@dataclass(frozen=True)
class Declared:
    """One declared activity. The two Art. 30 fields keep their provenance."""

    name: str
    purpose: Sourced
    legal_basis: Sourced
    domain: str = ""
    model: str = ""
    inputs: tuple[str, ...] = ()
    note: str = ""


def load(path: str | Path, *, vocabulary: Vocabulary) -> tuple[Declared, ...]:
    """Read a declared-activities document. What the user wrote raises."""
    origin = Path(path)
    raw = document.read(origin)
    return parse(raw, origin=str(origin), vocabulary=vocabulary)


def parse(
    raw: Mapping[str, Any] | None, *, origin: str, vocabulary: Vocabulary
) -> tuple[Declared, ...]:
    if raw is None:
        raise ConfigError(f"{origin} is empty")
    entries = raw.get("activities")
    if not isinstance(entries, Mapping) or not entries:
        raise ConfigError(f"{origin} has no `activities:` mapping")

    out = []
    for name, spec in entries.items():
        if not isinstance(spec, Mapping):
            raise ConfigError(f"activity {name!r} in {origin} should be a mapping")
        unknown = sorted(set(spec) - KEYS)
        if unknown:
            raise ConfigError(
                f"activity {name!r} in {origin} has unknown keys {', '.join(unknown)}. "
                f"Allowed: {', '.join(sorted(KEYS))}"
            )
        out.append(
            Declared(
                name=str(name),
                purpose=_sourced("purpose", spec, vocabulary),
                legal_basis=_sourced("legal_basis", spec, vocabulary),
                domain=_text(spec.get("domain")),
                model=_text(spec.get("model")),
                inputs=_inputs(spec.get("inputs"), name=str(name), origin=origin),
                note=_text(spec.get("note")),
            )
        )
    return tuple(sorted(out, key=lambda d: d.name))


def _sourced(key: str, spec: Mapping[str, Any], vocabulary: Vocabulary) -> Sourced:
    value = _text(spec.get(key))
    if not value:
        return Sourced("", Provenance.ABSENT)
    return Sourced(value, Provenance.DECLARED, vocabulary.unrecognised(key, value))


def _inputs(raw: Any, *, name: str, origin: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw.strip(),) if raw.strip() else ()
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return tuple(item.strip() for item in raw if item.strip())
    raise ConfigError(f"`inputs` for activity {name!r} in {origin} should be a list of strings")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
