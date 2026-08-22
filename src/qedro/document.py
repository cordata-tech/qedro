"""Reading a user-written document, whatever they chose to write it in.

Both of Qedro's user-authored inputs — the config and the vocabulary — are a
mapping of plain values. Nothing about either needs YAML specifically, so the
format is a preference rather than a constraint, and this module is the one
place that knows which formats exist.

**YAML, JSON and TOML all work today**, for both files. That is close to free:
YAML is a superset of JSON so one parser covers two, and TOML is in the standard
library. Dispatch is on the file suffix, falling back to YAML for a document
with no suffix to go on — a string handed over by a test, or eventually by a UI.

Adding a format later means adding a branch here and nothing else. That is the
point of the module existing rather than each loader calling a parser directly.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

#: Suffixes recognised, in the order a `qedro.*` file is looked for on disk.
#: YAML leads because it is what the documentation writes and what the ecosystem
#: expects; the others are there so nobody has to switch to use this tool.
SUFFIXES = (".yaml", ".yml", ".json", ".toml")


def parse(text: str, *, origin: str = "") -> Mapping[str, Any] | None:
    """Parse a document into a mapping, or None if it is empty.

    Empty is not an error. A placeholder config somebody committed intending to
    fill it in later is a reasonable thing to find, and refusing to start
    because of it helps nobody.

    Raises :class:`ConfigError` on anything unparseable or not shaped like a
    mapping — this is user input, and user input raises where evidence is
    counted.
    """
    label = origin or "the document"

    if Path(origin).suffix.lower() == ".toml":
        try:
            raw: Any = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{label} is not valid TOML: {exc}") from None
    else:
        # safe_load, never load: this is a file from the user's repository and
        # nothing in a config should be able to construct a Python object.
        # Also covers JSON, which YAML is a superset of.
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"{label} is not valid YAML or JSON: {exc}") from None

    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ConfigError(f"{label} should be a mapping at the top level")
    return raw


def read(path: Path) -> Mapping[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from None
    return parse(text, origin=str(path))


def alongside(directory: Path, stem: str) -> Path | None:
    """The first `<stem>.<suffix>` in *directory*, in :data:`SUFFIXES` order.

    Used to find `qedro.yaml` without requiring that it be YAML. Deterministic
    rather than glob order, so two machines with the same directory resolve the
    same file.
    """
    for suffix in SUFFIXES:
        candidate = directory / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return None
