"""Qedro — turns emitted evidence into the artefacts an auditor asks for."""

#: The single source. `pyproject.toml` reads this rather than restating it.
__version__ = "0.5.0"

#: U+220E END OF PROOF. Printed only when an artefact stands on its own
#: evidence — see `complete` in qedro.mark. Not decoration: withholding it is
#: the signal, so nothing should print it unconditionally.
TOMBSTONE = "∎"
