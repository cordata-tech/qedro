"""The mark is earned. These tests exist so that stays true."""

from qedro import TOMBSTONE
from qedro.mark import Completeness


def test_a_clean_run_earns_the_tombstone():
    assert Completeness().complete
    assert Completeness().suffix() == TOMBSTONE


def test_a_degraded_run_does_not():
    c = Completeness().degraded("purpose for 3 jobs came from the mapping file")
    assert not c.complete
    assert c.suffix() == ""


def test_the_reason_survives_so_the_summary_can_say_which():
    c = Completeness().degraded("no lineage for domain claims in window")
    assert c.reasons == ("no lineage for domain claims in window",)


def test_degrading_accumulates_rather_than_replacing():
    c = Completeness().degraded("one").degraded("two")
    assert c.reasons == ("one", "two")
    assert not c.complete


def test_ascii_fallback_for_terminals_without_the_glyph():
    assert Completeness().suffix(symbol=False) == "[complete]"
    assert Completeness().degraded("x").suffix(symbol=False) == ""


def test_the_tombstone_is_end_of_proof_not_black_square():
    # U+220E, not U+25A0. Semantically correct, and the distinction is easy
    # to lose to an editor's autocorrect.
    assert TOMBSTONE == "∎"
