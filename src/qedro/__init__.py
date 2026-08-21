"""Qedro — turns emitted evidence into the artefacts an auditor asks for."""

__version__ = "0.0.1"

#: U+220E END OF PROOF. Printed only when an artefact stands on its own
#: evidence — see `complete` in qedro.mark. Not decoration: withholding it is
#: the signal, so nothing should print it unconditionally.
TOMBSTONE = "∎"
