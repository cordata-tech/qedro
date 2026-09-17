"""What a run looked at, and what it could never have looked at.

Printed on **every** run of every projection, including one that earns the
tombstone. The mark is conditional and means *is what I found trustworthy*;
this is unconditional and means *what did I look at*. A scope statement that
appeared only when something was wrong would teach a reader that its absence
means full coverage, which is the invisible hole one level up. See
cordata-tech/qedro#3.

This started inside `ropa.py`. #3 asked whether `quality` and `provenance`
would need the same concept, and left it open on the grounds that guessing
would produce the wrong shape. `quality` needed it, so it moved here — with
the parts that are genuinely common in the base and the counts each projection
cares about in its own subclass. The shared part is *the window, the source,
the domains, and the standing sentence*; everything else differs, because what
counts as coverage differs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import words


@dataclass(frozen=True)
class Scope:
    """The part every projection's scope statement has in common."""

    source: str = ""
    since: datetime | None = None
    until: datetime | None = None
    events: int = 0
    domains_declared: tuple[str, ...] = ()
    domains_seen: tuple[str, ...] = ()
    #: Where each seen domain came from. A domain is in both when one job was
    #: mapped to it and another guessed into it. See cordata-tech/qedro#9.
    domains_guessed: tuple[str, ...] = ()
    domains_mapped: tuple[str, ...] = ()

    #: The standing sentence, overridden per projection. Deliberately factual
    #: about what was not examined rather than advisory about what that means
    #: for compliance — the second would be a legal interpretation, which a
    #: lawyer signs off and a CLI does not. See the open question on
    #: cordata-tech/qedro#3.
    OUT_OF_VIEW = (
        "This artefact covers what the pipelines that emit lineage reported. "
        "Systems that do not emit lineage are not represented here, and their "
        "absence is not evidence of their absence from the organisation."
    )

    @property
    def domains_silent(self) -> tuple[str, ...]:
        """Declared domains that produced nothing.

        The difference between *nothing happened* and *nothing was recorded*,
        which is invisible in the output unless something says it.
        """
        seen = set(self.domains_seen)
        return tuple(d for d in self.domains_declared if d not in seen)

    def domains_source(self) -> str:
        """Which domains in view were guessed and which were mapped, or "".

        Stated only when `domains:` is set, because that is when the guess
        decides the verdict: a job guessed into the wrong domain makes a
        declared one look silent, and without this line a wrong guess and a
        silent domain read the same. See cordata-tech/qedro#9.
        """
        if not self.domains_declared or not self.domains_seen:
            return ""
        parts = []
        if self.domains_guessed:
            parts.append(f"{', '.join(self.domains_guessed)} guessed from the job namespace")
        if self.domains_mapped:
            parts.append(f"{', '.join(self.domains_mapped)} from a mapping rule")
        return "; ".join(parts)

    def silent_reason(self) -> str:
        """The withholding reason for silent domains, or "" when none are.

        One copy for every projection that has domains. When any domain in view
        was guessed, the reason says so and names the override, since a wrong
        guess is the other way a domain comes to look silent.
        """
        if not self.domains_silent:
            return ""
        reason = (
            f"declared in scope but produced no lineage in the window: "
            f"{', '.join(self.domains_silent)}"
        )
        if self.domains_guessed:
            n = len(self.domains_guessed)
            reason += (
                f" — the {words.plural(n, 'domain', 'domains')} in view named "
                f"{', '.join(self.domains_guessed)} {words.plural(n, 'was', 'were')} guessed "
                "from the job namespace, and a wrong guess reads the same as silence; "
                "`domain:` on a mapping rule overrides the guess"
            )
        return reason

    def window(self) -> str:
        """The window as resolved, not as typed."""
        if self.since is None and self.until is None:
            return "all events available from the source"
        start = self.since.isoformat() if self.since else "the earliest event available"
        end = self.until.isoformat() if self.until else "the latest event available"
        return f"{start} to {end}"

    def lines(self) -> tuple[tuple[str, str], ...]:
        """Projection-specific summary lines, as label and value.

        Rendered in order by every format. Returning them from the scope rather
        than building them in each renderer is what keeps four formats and
        three projections from drifting into twelve slightly different
        summaries.
        """
        return ()
