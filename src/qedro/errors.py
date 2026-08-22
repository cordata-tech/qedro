"""The two things that can go wrong, and the line between them.

Parsing evidence never raises. A directory of production lineage holds events
from emitters that disagree with the spec, and a reader that dies on the first
of them is useless — bad records are skipped and counted, and the count reaches
the completeness decision. Same for a backend that returns a page of nonsense.

What the *user wrote* is the opposite. A source address or a config file comes
from the person running the command, and a typo they cannot see is worse than a
traceback: it silently produces an artefact with a hole in it. Those raise,
with the offending text named.
"""

from __future__ import annotations


class QedroError(Exception):
    """Base for anything this tool raises on purpose."""


class ConfigError(QedroError):
    """Something the user wrote is not usable as written.

    A source address, a ``qedro.yaml``, a vocabulary document. Not evidence —
    evidence is skipped and counted, never raised on.
    """


class UsageError(QedroError):
    """The command is well-formed but the combination cannot be carried out.

    Separate from :class:`ConfigError` because nothing the user wrote is
    *wrong* — ``--format xlsx`` with no ``--out`` is a sound request with
    nowhere to put the answer. Raised before any evidence is read, so the
    failure arrives in the first millisecond rather than after a run against a
    remote backend.
    """
