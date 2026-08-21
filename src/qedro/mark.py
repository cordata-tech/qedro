"""The tombstone, and the rule about when it may be shown.

The wordmark is ``QEDR∎``. The mark means *this artefact stands on its own
evidence*, so a run that fell back to a mapping file, or that covered a domain
with no lineage in the window, must not print it. The run still succeeds and
still writes the file — it simply does not claim to be a proof.

Withholding is the whole point. A mark printed on every successful run says
nothing, and a compliance artefact with invisible holes is worse than none.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import TOMBSTONE


@dataclass(frozen=True)
class Completeness:
    """Why a run may or may not claim to be a proof.

    Reasons are recorded rather than counted so the summary can say which
    condition applied. "Incomplete" with no explanation is not actionable.
    """

    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        return not self.reasons

    def degraded(self, reason: str) -> Completeness:
        return Completeness(reasons=self.reasons + (reason,))

    def suffix(self, *, symbol: bool = True) -> str:
        """The trailing mark for a CLI summary line, or an empty string.

        ``symbol=False`` covers terminals and CI logs with no glyph for
        U+220E, where the character renders as tofu and reads as a bug.
        """
        if not self.complete:
            return ""
        return TOMBSTONE if symbol else "[complete]"
