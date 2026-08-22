"""The Art. 30 projection.

Two things carry most of the weight here: **provenance precedence** — a facet
beats the mapping file, always — and **the tombstone rule**, which is the one a
future simplification would quietly break. The tests for the mark are written in
both directions on purpose: several for each condition that withholds it, and
one that it *is* printed when everything is evidenced. Without the second, a
change that withheld the mark unconditionally would pass.
"""

from __future__ import annotations

from datetime import UTC, datetime

from qedro import config, vocabulary
from qedro.events import parse_event
from qedro.ropa import Provenance, build
from qedro.sources import ReadReport

WORDS = vocabulary.load()


def event(name="scored", namespace="acme.fraud", facet=None, when="2026-03-01T10:00:00Z", run="r1"):
    raw = {
        "eventType": "COMPLETE",
        "eventTime": when,
        "run": {"runId": run},
        "job": {"namespace": namespace, "name": name, "facets": {}},
        "inputs": [{"namespace": "wh", "name": "raw.customers"}],
        "outputs": [{"namespace": "wh", "name": "curated.scores"}],
    }
    if facet:
        raw["job"]["facets"]["processing"] = {
            "_producer": "https://example.test",
            "_schemaURL": "https://example.test/s.json",
            **facet,
        }
    parsed = parse_event(raw)
    assert parsed is not None
    return parsed


EVIDENCED = {"purpose": "fraud-detection", "legal_basis": "legitimate-interest"}


#: Art. 30(1)(a) is its own withholding condition, so a test that is about
#: anything else has to declare a controller or it can never reach a complete
#: record. Supplied by default here and asserted on its own below.
CONTROLLER = "controller: ACME GmbH\n"


def record(events, *, cfg="", report=None, **kw):
    if "controller" not in cfg:
        cfg = CONTROLLER + cfg
    return build(events, config=config.parse(cfg), vocabulary=WORDS, report=report, **kw)


class TestProvenancePrecedence:
    def test_an_emitted_facet_is_evidence(self):
        [activity] = record([event(facet=EVIDENCED)]).activities
        assert activity.purpose.provenance is Provenance.FACET
        assert activity.evidenced

    def test_the_mapping_file_fills_a_gap_but_is_not_evidence(self):
        out = record(
            [event()],
            cfg='jobs:\n  "acme.fraud/*": {purpose: p, legal_basis: consent}\n',
        )
        [activity] = out.activities
        assert activity.purpose.value == "p"
        assert activity.purpose.provenance is Provenance.MAPPING
        assert not activity.evidenced

    def test_the_facet_wins_when_both_exist(self):
        # The file cannot overrule the pipeline. A config that could silently
        # rewrite emitted evidence would make the record unfalsifiable.
        out = record(
            [event(facet=EVIDENCED)],
            cfg='jobs:\n  "acme.fraud/*": {purpose: from-the-file}\n',
        )
        [activity] = out.activities
        assert activity.purpose.value == "fraud-detection"
        assert activity.purpose.provenance is Provenance.FACET

    def test_the_two_fields_are_tracked_separately(self):
        # A half-emitted facet is real: an emitter may declare purpose and
        # leave legal basis to the controller.
        out = record(
            [event(facet={"purpose": "fraud-detection"})],
            cfg='jobs:\n  "acme.fraud/*": {legal_basis: consent}\n',
        )
        [activity] = out.activities
        assert activity.purpose.provenance is Provenance.FACET
        assert activity.legal_basis.provenance is Provenance.MAPPING
        assert not activity.evidenced

    def test_nothing_anywhere_is_absent_not_empty(self):
        [activity] = record([event()]).activities
        assert activity.purpose.provenance is Provenance.ABSENT
        assert "no purpose declared" in activity.gaps()

    def test_a_facet_on_a_later_event_still_counts(self):
        # Emitters attach facets to COMPLETE but not START, and the projection
        # should not depend on which event happened to sort first.
        events = [event(when="2026-03-01T09:00:00Z"), event(facet=EVIDENCED)]
        [activity] = record(events).activities
        assert activity.evidenced


class TestTheTombstoneIsEarned:
    def test_it_is_printed_when_every_activity_is_evidenced(self):
        # The test a future simplification breaks first. Without it, code that
        # withheld the mark unconditionally would pass every other test here.
        assert record([event(facet=EVIDENCED)]).complete

    def test_withheld_when_anything_came_from_the_mapping_file(self):
        out = record(
            [event(facet=EVIDENCED), event(name="other")],
            cfg='jobs:\n  "acme.fraud/other": {purpose: p, legal_basis: consent}\n',
        )
        assert not out.complete
        assert any("mapping file" in r for r in out.completeness.reasons)

    def test_withheld_when_a_field_is_undeclared_everywhere(self):
        out = record([event()])
        assert not out.complete
        assert any("no purpose or no legal basis" in r for r in out.completeness.reasons)

    def test_withheld_when_a_declared_domain_produced_no_lineage(self):
        out = record([event(facet=EVIDENCED)], cfg="domains: [fraud, marketing]\n")
        assert not out.complete
        assert any("marketing" in r for r in out.completeness.reasons)

    def test_withheld_when_a_value_is_outside_the_vocabulary(self):
        out = record([event(facet={"purpose": "p", "legal_basis": "vibes"})])
        assert not out.complete
        assert any("vocabulary does not define" in r for r in out.completeness.reasons)

    def test_withheld_when_no_controller_is_declared(self):
        # Art. 30(1)(a). Without a controller the document is not an Art. 30
        # record at all, which is a bigger hole than any single missing field.
        out = build([event(facet=EVIDENCED)], config=config.Config(), vocabulary=WORDS)
        assert not out.complete
        assert any("Art. 30(1)(a)" in r for r in out.completeness.reasons)

    def test_withheld_when_nothing_was_found_at_all(self):
        out = record([])
        assert not out.complete
        assert any("not the same as nothing having happened" in r for r in out.completeness.reasons)

    def test_withheld_when_the_read_itself_was_incomplete(self):
        # A projection built on 900 of 1,000 events is not a proof of anything,
        # and the reason has to reach the artefact rather than stopping at the
        # reader.
        out = record([event(facet=EVIDENCED)], report=ReadReport(skipped_records=3))
        assert not out.complete
        assert any("not usable OpenLineage events" in r for r in out.completeness.reasons)

    def test_every_reason_is_a_sentence_a_reviewer_can_act_on(self):
        out = record([event()], cfg="domains: [fraud, marketing]\n")
        assert not out.complete
        for reason in out.completeness.reasons:
            assert len(reason.split()) > 3, f"{reason!r} does not explain anything"


class TestTheScopeStatement:
    """cordata-tech/qedro#3 — unconditional, unlike the mark."""

    def test_it_is_present_on_a_run_that_earns_the_tombstone(self):
        # The case a simplification drops first: if scope only appeared when
        # something was wrong, its absence would read as full coverage.
        out = record([event(facet=EVIDENCED)])
        assert out.complete
        assert out.scope.jobs == 1
        assert out.scope.OUT_OF_VIEW

    def test_the_window_is_what_was_resolved_not_what_was_typed(self):
        out = record([event(when="2026-03-01T10:00:00Z")])
        assert out.scope.since == datetime(2026, 3, 1, 10, 0, tzinfo=UTC)

    def test_an_explicit_window_is_kept_as_asked(self):
        asked = datetime(2026, 1, 1, tzinfo=UTC)
        out = record([event()], since=asked)
        assert out.scope.since == asked

    def test_it_counts_the_provenance_mix(self):
        # A proportion, unlike the mark, which is binary. "41 of 47 evidenced"
        # points a reviewer somewhere; a missing glyph does not.
        out = record(
            [event(facet=EVIDENCED), event(name="b"), event(name="c")],
            cfg='jobs:\n  "acme.fraud/b": {purpose: p, legal_basis: consent}\n',
        )
        assert (out.scope.evidenced, out.scope.from_mapping, out.scope.undeclared) == (1, 1, 1)

    def test_a_silent_domain_is_named(self):
        out = record([event(facet=EVIDENCED)], cfg="domains: [fraud, marketing, hr]\n")
        assert out.scope.domains_silent == ("marketing", "hr")

    def test_no_declared_domains_means_nothing_is_silent(self):
        assert record([event(facet=EVIDENCED)]).scope.domains_silent == ()


class TestGroupingAndIdentity:
    def test_one_activity_per_job_across_events(self):
        events = [event(run="r1"), event(run="r2"), event(name="other")]
        out = record(events)
        assert len(out.activities) == 2
        scored = next(a for a in out.activities if a.name == "scored")
        assert scored.runs == 2
        assert scored.events == 2

    def test_activities_are_ordered_by_job_key(self):
        # Stable output matters: a record whose row order changes between runs
        # produces a diff nobody can review.
        out = record([event(name="zeta"), event(name="alpha")])
        assert [a.name for a in out.activities] == ["alpha", "zeta"]

    def test_namespace_is_part_of_identity(self):
        # Two domains can both run a job called `scored` and they are not the
        # same processing activity.
        out = record([event(namespace="acme.fraud"), event(namespace="acme.policy")])
        assert len(out.activities) == 2

    def test_datasets_are_deduplicated_across_runs(self):
        [activity] = record([event(run="r1"), event(run="r2")]).activities
        assert activity.inputs == ("wh/raw.customers",)

    def test_the_domain_comes_off_the_namespace(self):
        [activity] = record([event(namespace="acme.fraud")]).activities
        assert activity.domain == "fraud"

    def test_a_rule_overrides_the_domain_guess(self):
        # The guess is a heuristic and a wrong one silently changes which
        # domains look silent, so it has to be overridable.
        out = record(
            [event(namespace="weird_ns")],
            cfg='jobs:\n  "weird_ns/*": {domain: fraud}\n',
        )
        assert out.activities[0].domain == "fraud"


class TestTheReasonsReadLikeSentences:
    """`1 of 4 activities relies`, not `1 of 4 activities rely`.

    Small, and the kind of small that costs a tool its authority — the same
    reason `_count` exists in the CLI. These strings are the entire explanation
    a reviewer gets when the mark is withheld, so they are the last place to be
    careless. Note the two agreements pull in different directions: the noun
    goes with the total, the verb with the count.
    """

    def reasons(self, out) -> str:
        return " ".join(out.completeness.reasons)

    def test_one_activity_of_several_relies(self):
        events = [event(name=n, facet=EVIDENCED) for n in "abc"] + [event(name="d")]
        out = record(events, cfg='jobs:\n  "*d": {purpose: p, legal_basis: consent}\n')
        assert "1 of 4 activities relies on the mapping file" in self.reasons(out)
        assert "that entry is asserted" in self.reasons(out)

    def test_several_of_several_rely(self):
        events = [event(name=n, facet=EVIDENCED) for n in "ab"] + [event(name=n) for n in "cd"]
        out = record(events, cfg='jobs:\n  "*": {purpose: p, legal_basis: consent}\n')
        assert "2 of 4 activities rely on the mapping file" in self.reasons(out)
        assert "those entries are asserted" in self.reasons(out)

    def test_one_activity_has_no_declaration(self):
        out = record([event(name="a", facet=EVIDENCED), event(name="b")])
        assert "1 of 2 activities has no purpose or no legal basis" in self.reasons(out)

    def test_one_activity_carries_an_unknown_value(self):
        out = record([event(facet={"purpose": "p", "legal_basis": "vibes"})])
        assert "1 activity carries a value the vocabulary does not define" in self.reasons(out)
