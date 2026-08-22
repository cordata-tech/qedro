"""The vocabulary, loaded as a document.

The commitment this module exists to keep: **the vocabulary is data the tool
loads, never types the tool is compiled against.** Three separate requirements
land on that one decision — source-neutrality, organisations authoring their own
ontologies later, and shipping recommended starter ontologies. All three are
free if a vocabulary is a document read at runtime. All three need a rewrite of
everything touching a term if `legal_basis` is a Python enum.

So there is no enum here, and there is no list of the six lawful bases in this
file. There is a loader, and a document under ``vocabularies/`` that a user can
replace wholesale. ``tests/test_vocabulary.py`` asserts the shipped document
agrees with the generated facet schema, so the two cannot drift — a test rather
than an import, because an import would be the compiled coupling this module is
here to avoid.

A term is either **closed** or **open**. Closed means a value outside the set is
a finding worth surfacing; ``legal_basis`` is closed because Art. 6(1) enumerates
exactly six bases. Open means the set is illustrative and an unlisted value is
perfectly normal; ``purpose`` is open because an organisation's purposes are its
own. Nothing here rejects a value either way — reporting an unrecognised term is
the projection's business, and refusing to read evidence is nobody's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

from . import document
from .errors import ConfigError

#: The document loaded when nobody asks for another one.
DEFAULT = "dsgvo.yaml"


@dataclass(frozen=True)
class Term:
    """One key in the vocabulary, and what its values mean."""

    key: str
    description: str = ""
    closed: bool = False
    values: Mapping[str, str] = field(default_factory=dict)

    def knows(self, value: str) -> bool:
        return value in self.values

    def means(self, value: str) -> str | None:
        return self.values.get(value)

    def unrecognised(self, value: str) -> bool:
        """Whether this value is worth surfacing to a reviewer.

        Only closed terms can produce one. An unlisted ``purpose`` is the normal
        case and flagging it would train a reader to ignore the flag.
        """
        return self.closed and not self.knows(value)


@dataclass(frozen=True)
class Vocabulary:
    name: str
    description: str = ""
    version: int = 1
    origin: str = ""
    terms: Mapping[str, Term] = field(default_factory=dict)

    def term(self, key: str) -> Term | None:
        return self.terms.get(key)

    def unrecognised(self, key: str, value: str) -> bool:
        """True when *value* is outside a closed term's set.

        A key the vocabulary has never heard of returns False. Qedro reporting a
        term this vocabulary does not define is not the vocabulary's business,
        and treating silence as rejection would make every ontology that omits a
        key look like it forbade it.
        """
        term = self.terms.get(key)
        return term is not None and term.unrecognised(value)


def load(path: str | Path | None = None) -> Vocabulary:
    """Load a vocabulary document, or the shipped default.

    Raises :class:`ConfigError` for a document that cannot be read or is not
    shaped like a vocabulary — that is something the user wrote, and the rule
    is that user input raises where evidence is counted.
    """
    if path is None:
        source = resources.files(f"{__package__}.vocabularies").joinpath(DEFAULT)
        return parse(source.read_text(encoding="utf-8"), origin=f"{DEFAULT} (shipped)")

    file = Path(path)
    return _build(document.read(file), origin=str(file))


def parse(text: str, *, origin: str = "") -> Vocabulary:
    """Parse a vocabulary document — YAML, JSON or TOML, per *origin*'s suffix.

    Separate from :func:`load` so tests and a future UI can hand over a string
    without inventing a file.
    """
    return _build(document.parse(text, origin=origin), origin=origin)


def _build(raw: Mapping[str, Any] | None, *, origin: str) -> Vocabulary:
    if raw is None:
        raise ConfigError(f"{origin or 'the vocabulary'} is empty")

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ConfigError(f"{origin or 'the vocabulary'} has no `name`")

    terms_raw = raw.get("terms", {})
    if not isinstance(terms_raw, Mapping):
        raise ConfigError(f"`terms` in {origin or 'the vocabulary'} should be a mapping")

    terms = {}
    for key, spec in terms_raw.items():
        if not isinstance(key, str):
            continue
        terms[key] = _term(key, spec, origin)

    version = raw.get("version")
    return Vocabulary(
        name=name,
        description=_str(raw.get("description")),
        version=version if isinstance(version, int) else 1,
        origin=origin,
        terms=terms,
    )


def _term(key: str, spec: Any, origin: str) -> Term:
    if not isinstance(spec, Mapping):
        raise ConfigError(f"term `{key}` in {origin or 'the vocabulary'} should be a mapping")

    values_raw = spec.get("values") or {}
    if not isinstance(values_raw, Mapping):
        raise ConfigError(f"`values` for term `{key}` should be a mapping")

    # A value may be spelled `name: {means: ...}` or bare `name:` with nothing
    # under it. The second is a legitimate way to write a vocabulary whose
    # values need no gloss, and rejecting it would make the format fussier
    # than the thing it describes.
    values = {}
    for value, meaning in values_raw.items():
        if not isinstance(value, str):
            continue
        if isinstance(meaning, Mapping):
            values[value] = _str(meaning.get("means"))
        else:
            values[value] = _str(meaning)

    return Term(
        key=key,
        description=_str(spec.get("description")),
        closed=bool(spec.get("closed", False)),
        values=values,
    )


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
