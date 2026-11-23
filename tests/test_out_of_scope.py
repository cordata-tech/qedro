"""A job the mapping file says processes no personal data (#65).

On a platform that also runs pipelines over non-personal data — fund prices,
sensor readings — those jobs would otherwise be activities with no purpose and no
legal basis, and withhold the mark for a gap that is not one. A rule can leave
them out, and the record then says what it left out and why, in every format,
rather than leaving it out silently. A job left out this way that touches a
dataset classified as personal data is a contradiction, and withholds the mark.
"""

from __future__ import annotations

import json

import pytest

from qedro import config, render, vocabulary
from qedro.errors import ConfigError
from qedro.ropa import Record

from .as_text import as_text
from .test_ropa import EVIDENCED, record, tagged

FORMATS = [fmt for fmt in sorted(render.FORMATS) if render.supports(fmt, Record)]

FUNDS = '"acme.fraud/fund_*"'
RULE = f"jobs:\n  {FUNDS}:\n    out_of_scope: fund prices and figures, no personal data\n"


def built(*events, cfg=RULE):
    return record(list(events), cfg=cfg)


def a_fund_job(name="fund_prices", writes=(("wh/funds.prices", {}),)):
    return tagged(name=name, writes=writes, facet=None)


class TestLeftOut:
    def test_a_job_an_out_of_scope_rule_matches_is_not_an_activity(self):
        out = built(tagged(name="scored", writes=(("wh/scores", {}),)), a_fund_job())
        assert [a.name for a in out.activities] == ["scored"]

    def test_the_record_lists_it_with_the_rules_reason(self):
        [left] = built(a_fund_job()).scope.left_out
        assert left.job == "acme.fraud/fund_prices"
        assert left.reason == "fund prices and figures, no personal data"
        assert left.pattern == "acme.fraud/fund_*"

    def test_it_does_not_withhold_the_mark_for_its_missing_purpose(self):
        # The point of the rule: the job has no purpose and no legal basis, and
        # without the rule that withholds the mark for a gap that is not one.
        out = built(tagged(name="scored", writes=(("wh/scores", {}),)), a_fund_job())
        assert out.complete, out.completeness.reasons

    def test_without_the_rule_the_same_job_withholds_it(self):
        # The other direction: the test above passes only because of the rule.
        out = built(tagged(name="scored", writes=(("wh/scores", {}),)), a_fund_job(), cfg="")
        assert not out.complete

    def test_it_still_counts_as_a_job_that_was_looked_at(self):
        out = built(tagged(name="scored", writes=(("wh/scores", {}),)), a_fund_job())
        assert out.scope.jobs == 2

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_every_format_says_what_was_left_out_and_why(self, fmt):
        out = built(tagged(name="scored", writes=(("wh/scores", {}),)), a_fund_job())
        text = as_text(render.FORMATS[fmt](out))
        assert "acme.fraud/fund_prices" in text
        assert "fund prices and figures, no personal data" in text

    def test_the_json_lists_it_beside_the_fields_a_sign_off_covers(self):
        out = built(tagged(name="scored", writes=(("wh/scores", {}),)), a_fund_job())
        payload = json.loads(render.FORMATS["json"](out))
        assert payload["scope"]["left_out"] == [
            {
                "job": "acme.fraud/fund_prices",
                "reason": "fund prices and figures, no personal data",
                "rule": "acme.fraud/fund_*",
                "personal_data": [],
            }
        ]
        assert [a["job"] for a in payload["activities"]] == ["acme.fraud/scored"]


class TestContradiction:
    def test_a_left_out_job_touching_personal_data_withholds_the_mark(self):
        job = a_fund_job(writes=(("wh/funds.holders", {"data_category": "contact"}),))
        out = built(tagged(name="scored", writes=(("wh/scores", {}),)), job)
        [left] = out.scope.left_out
        assert left.personal_data == (("wh/funds.holders", "data_category", "contact"),)
        assert not out.complete
        [reason] = [r for r in out.completeness.reasons if "left out" in r]
        assert "acme.fraud/fund_prices, which touches wh/funds.holders (data_category contact)" in (
            reason
        )
        # And the JSON gives each finding as fields, so a consumer parses no prose.
        payload = json.loads(render.FORMATS["json"](out))
        assert payload["scope"]["left_out"][0]["personal_data"] == [
            {"dataset": "wh/funds.holders", "key": "data_category", "value": "contact"}
        ]

    def test_reading_it_counts_as_much_as_writing_it(self):
        job = tagged(
            name="fund_prices",
            reads=(("wh/customers", {"subject_type": "customer"}),),
            writes=(("wh/funds.prices", {}),),
            facet=None,
        )
        assert not built(tagged(name="scored", writes=(("wh/scores", {}),)), job).complete

    def test_data_the_vocabulary_says_is_not_personal_is_no_contradiction(self):
        # `subject_type: none` is flagged `personal: false` in the shipped
        # vocabulary: someone said the table holds no personal data, which is
        # what the rule claims too.
        job = a_fund_job(writes=(("wh/funds.prices", {"subject_type": "none"}),))
        out = built(tagged(name="scored", writes=(("wh/scores", {}),)), job)
        assert out.scope.left_out[0].personal_data == ()
        assert out.complete, out.completeness.reasons

    def test_a_classification_outside_art_30_1_c_is_no_contradiction(self):
        # Where data sits and how long it is kept say nothing about whether it
        # is personal; only what answers Art. 30(1)(c) does.
        job = a_fund_job(writes=(("wh/funds.prices", {"residency": "eu"}),))
        assert built(tagged(name="scored", writes=(("wh/scores", {}),)), job).complete


class TestTheRule:
    def test_out_of_scope_takes_a_reason(self):
        with pytest.raises(ConfigError, match="out_of_scope` .* should say why"):
            config.parse(f"jobs:\n  {FUNDS}:\n    out_of_scope: true\n")

    def test_an_empty_reason_is_refused(self):
        # A job left out with no reason would be left out silently, which is
        # what the rule exists to prevent.
        with pytest.raises(ConfigError, match="out_of_scope` .* should say why"):
            config.parse(f'jobs:\n  {FUNDS}:\n    out_of_scope: ""\n')

    def test_it_cannot_also_give_a_purpose(self):
        # Out of scope and a purpose contradict each other in the one rule.
        with pytest.raises(ConfigError, match="out_of_scope` cannot also"):
            config.parse(f"jobs:\n  {FUNDS}:\n    out_of_scope: x\n    purpose: p\n")


class TestTheVocabularyFlag:
    def test_the_shipped_vocabulary_flags_subject_type_none(self):
        words = vocabulary.load()
        assert not words.personal("subject_type", "none")
        assert words.personal("subject_type", "customer")

    def test_a_key_or_value_the_vocabulary_does_not_flag_counts_as_personal(self):
        # Silence is not a claim that data is not personal.
        words = vocabulary.load()
        assert words.personal("data_category", "contact")
        assert words.personal("nonexistent", "x")

    def test_the_flag_must_be_true_or_false(self):
        with pytest.raises(ConfigError, match="personal"):
            vocabulary.parse(
                "name: v\nterms:\n  subject_type:\n    values:\n      none: {personal: no-thanks}\n",
                origin="v.yaml",
            )


def test_an_evidenced_left_out_job_is_still_left_out():
    # A rule that leaves a job out wins over a facet the job emitted: the rule is
    # the controller saying the processing is not in this record's scope, and the
    # record says so beside the job's name.
    out = built(tagged(name="fund_prices", writes=(("wh/funds.prices", {}),), facet=EVIDENCED))
    assert out.activities == ()
    assert out.scope.left_out[0].job == "acme.fraud/fund_prices"
