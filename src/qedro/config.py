"""`qedro.yaml` — the controller, the scope, and the mapping fallback.

Three things live here, and only the first is required:

    controller:            # who the record belongs to. Art. 30(1)(a).
      name: ACME GmbH
      contact: dpo@acme.example

    domains:               # what should be in the record, whether or not
      - fraud              # anything was emitted for it. Naming a domain that
      - marketing          # produced no lineage is how the silence becomes
                           # visible instead of invisible.

    jobs:                  # the fallback, for pipelines that emit no facet
      "cordata.fraud/*":
        purpose: fraud-detection
        legal_basis: legitimate-interest

**The mapping is a fallback and is treated as one.** A purpose read from this
file is an assertion by whoever wrote the file; a purpose read from an emitted
facet is evidence produced by the thing that ran. The projection keeps the two
apart all the way to the output, and any use of this file withholds the
tombstone. That is not a limitation to be engineered away — it is the file
being honest about what it is.

Patterns are fnmatch, tried against ``namespace/name`` first and then the bare
name, with **first match in file order winning**. Order in the document is the
order in the file, because every format :mod:`qedro.document` reads preserves
it; that is deliberate, so a reader can resolve a job by reading down the page
rather than by working out a specificity rule.

The file is called `qedro.yaml` throughout the documentation, but **YAML, JSON
and TOML are all read** — see :mod:`qedro.document`. Nothing here depends on
which was chosen.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from . import document
from .errors import ConfigError

#: Looked for in the working directory when `--config` is not given, with any
#: suffix :mod:`qedro.document` understands. Absent is not an error: a run
#: against pipelines that all emit the facet needs no mapping at all, and that
#: is the case worth making easy.
STEM = "qedro"

#: What a `jobs:` entry may declare. Anything else is a typo the user wants to
#: hear about rather than a silently ignored key.
RULE_KEYS = frozenset({"purpose", "legal_basis", "domain"})


@dataclass(frozen=True)
class Controller:
    """Art. 30(1)(a) — the controller's identity, as written by the controller.

    Not derived from anything and not guessable. A record with no controller on
    it is not an Art. 30 record, which is why this is the one required section.
    """

    name: str
    contact: str = ""
    representative: str = ""
    dpo: str = ""

    def __bool__(self) -> bool:
        return bool(self.name)


@dataclass(frozen=True)
class Rule:
    """One `jobs:` entry."""

    pattern: str
    purpose: str = ""
    legal_basis: str = ""
    domain: str = ""

    def matches(self, namespace: str, name: str) -> bool:
        return fnmatchcase(f"{namespace}/{name}", self.pattern) or fnmatchcase(name, self.pattern)


@dataclass(frozen=True)
class Config:
    controller: Controller = field(default_factory=lambda: Controller(""))
    domains: tuple[str, ...] = ()
    rules: tuple[Rule, ...] = ()
    vocabulary: str = ""
    origin: str = ""

    @property
    def present(self) -> bool:
        """Whether a config was actually found, as opposed to defaulted."""
        return bool(self.origin)

    def rule_for(self, namespace: str, name: str) -> Rule | None:
        """First match in file order, or None."""
        for rule in self.rules:
            if rule.matches(namespace, name):
                return rule
        return None

    def domain_for(self, namespace: str, rule: Rule | None = None) -> str:
        """Which domain a job in *namespace* belongs to.

        A heuristic — the last segment, so `acme.fraud` reads as `fraud` — and
        a mapping rule's `domain:` overrides it. Kept simple and overridable
        rather than clever, because a wrong guess here silently changes which
        domains look silent.

        Lives on `Config` because more than one projection needs the same
        answer, and two projections disagreeing about which domain a job is in
        would be a bug nobody would think to look for.
        """
        if rule is not None and rule.domain:
            return rule.domain
        for separator in ("/", "."):
            if separator in namespace:
                return namespace.rsplit(separator, 1)[-1]
        return namespace

    @staticmethod
    def domain_guessed(rule: Rule | None) -> bool:
        """Whether `domain_for` guessed, rather than read a rule's `domain:`.

        An integration that names its namespace after itself — openlineage-dbt
        defaults to `dbt` — puts every job in one guessed domain, and a declared
        domain then looks silent although its jobs emitted lineage. The guess is
        not improved here; it is made visible. See cordata-tech/qedro#9.
        """
        return not (rule is not None and rule.domain)


def find(explicit: str | Path | None, *, start: Path | None = None) -> Path | None:
    """Locate a config file.

    An explicit path that does not exist is an error — the user named a file and
    meant it. An absent default is simply absent.
    """
    if explicit is not None:
        path = Path(explicit)
        if not path.is_file():
            raise ConfigError(f"no config file at {path}")
        return path

    return document.alongside(start or Path.cwd(), STEM)


def load(path: str | Path | None) -> Config:
    """Load a config, or return an empty one when there is nothing to load."""
    if path is None:
        return Config()

    file = Path(path)
    return _build(document.read(file), origin=str(file))


def parse(text: str, *, origin: str = "qedro.yaml") -> Config:
    """Parse a config from text. Format follows *origin*'s suffix — see
    :mod:`qedro.document`."""
    return _build(document.parse(text, origin=origin), origin=origin)


def _build(raw: Mapping[str, Any] | None, *, origin: str) -> Config:
    # An empty file is a legitimate thing to commit — a placeholder somebody
    # will fill in — and is not worth an error.
    if raw is None:
        return Config(origin=origin)

    return Config(
        controller=_controller(raw.get("controller"), origin),
        domains=_domains(raw.get("domains"), origin),
        rules=_rules(raw.get("jobs"), origin),
        vocabulary=_str(raw.get("vocabulary")),
        origin=origin,
    )


def _controller(raw: Any, origin: str) -> Controller:
    if raw is None:
        return Controller("")
    if isinstance(raw, str):
        # `controller: ACME GmbH` is what people write first, and reading it as
        # the name costs nothing.
        return Controller(raw.strip())
    if not isinstance(raw, Mapping):
        raise ConfigError(f"`controller` in {origin} should be a name or a mapping")

    name = _str(raw.get("name"))
    if not name:
        raise ConfigError(f"`controller` in {origin} has no `name`")
    return Controller(
        name=name,
        contact=_str(raw.get("contact")),
        representative=_str(raw.get("representative")),
        dpo=_str(raw.get("dpo")),
    )


def _domains(raw: Any, origin: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw.strip(),)
    if not isinstance(raw, list):
        raise ConfigError(f"`domains` in {origin} should be a list")
    return tuple(d.strip() for d in raw if isinstance(d, str) and d.strip())


def _rules(raw: Any, origin: str) -> tuple[Rule, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Mapping):
        raise ConfigError(f"`jobs` in {origin} should be a mapping of pattern to fields")

    rules = []
    for pattern, spec in raw.items():
        if not isinstance(pattern, str):
            continue
        if not isinstance(spec, Mapping):
            raise ConfigError(f"`jobs: {pattern}` in {origin} should be a mapping")

        unknown = sorted(set(spec) - RULE_KEYS)
        if unknown:
            raise ConfigError(
                f"`jobs: {pattern}` in {origin} has unknown keys: {', '.join(unknown)}. "
                f"Allowed: {', '.join(sorted(RULE_KEYS))}"
            )

        rules.append(
            Rule(
                pattern=pattern,
                purpose=_str(spec.get("purpose")),
                legal_basis=_str(spec.get("legal_basis")),
                domain=_str(spec.get("domain")),
            )
        )
    return tuple(rules)


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
