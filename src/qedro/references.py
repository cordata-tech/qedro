"""What each field of a record answers in the regulation, in its own words (#48).

Loaded at runtime from a document, like the vocabulary, so a record can be
mapped to another regulation without a code change. The GDPR's ships as the
default, in `regulations/gdpr.yaml`.

A reference is a citation and the regulation's wording, quoted. Nothing here
interprets it: an explanation says which requirement a field answers, never
whether the value meets it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from . import document
from .errors import ConfigError

DEFAULT = "gdpr.yaml"


@dataclass(frozen=True)
class Reference:
    """One requirement: how it is cited, and its wording."""

    id: str
    cite: str
    text: str


@dataclass(frozen=True)
class References:
    name: str = ""
    regulation: str = ""
    source: str = ""
    by_id: Mapping[str, Reference] = field(default_factory=dict)
    #: Field name to reference id. A field that answers nothing is absent.
    fields: Mapping[str, str] = field(default_factory=dict)
    origin: str = ""

    def answers(self, field_name: str) -> Reference | None:
        """The requirement a field answers, or None where the document names none."""
        ref = self.fields.get(field_name)
        return self.by_id.get(ref) if ref else None


def load(path: str | Path | None = None) -> References:
    """Load a references document, or the shipped GDPR one.

    A document the user wrote raises :class:`ConfigError` when it cannot be
    read or is not shaped like one, as every user-written input does.
    """
    if path is None:
        source = resources.files(f"{__package__}.regulations").joinpath(DEFAULT)
        return parse(source.read_text(encoding="utf-8"), origin=f"{DEFAULT} (shipped)")
    file = Path(path)
    return _build(document.read(file), origin=str(file))


def parse(text: str, *, origin: str = "") -> References:
    return _build(document.parse(text, origin=origin), origin=origin)


def _build(raw: Mapping[str, Any] | None, *, origin: str) -> References:
    if raw is None:
        raise ConfigError(f"{origin or 'the references document'} is empty")
    entries = raw.get("references")
    if not isinstance(entries, Mapping) or not entries:
        raise ConfigError(f"{origin} has no `references:` mapping")

    by_id: dict[str, Reference] = {}
    for ref_id, spec in entries.items():
        if not isinstance(spec, Mapping):
            raise ConfigError(f"reference {ref_id!r} in {origin} should be a mapping")
        cite, text = spec.get("cite"), spec.get("text")
        if not isinstance(cite, str) or not cite.strip():
            raise ConfigError(f"reference {ref_id!r} in {origin} has no `cite:`")
        if not isinstance(text, str) or not text.strip():
            # The wording is the point: a citation alone asks the reader to
            # look it up, and the issue was a record a non-engineer can read.
            raise ConfigError(f"reference {ref_id!r} in {origin} has no `text:`")
        by_id[str(ref_id)] = Reference(str(ref_id), cite.strip(), " ".join(text.split()))

    fields = raw.get("fields") or {}
    if not isinstance(fields, Mapping):
        raise ConfigError(f"`fields` in {origin} should be a mapping of field to reference")
    for name, ref_id in fields.items():
        if ref_id not in by_id:
            raise ConfigError(
                f"`fields: {name}` in {origin} names {ref_id!r}, which is not under `references:`"
            )

    return References(
        name=str(raw.get("name") or ""),
        regulation=str(raw.get("regulation") or ""),
        source=str(raw.get("source") or ""),
        by_id=by_id,
        fields={str(k): str(v) for k, v in fields.items()},
        origin=origin,
    )
