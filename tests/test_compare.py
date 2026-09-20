"""Comparing two records — cordata-tech/qedro#14.

Two things carry the weight here. **A provenance regression is a finding even
when the value did not change**, which is the whole reason the command exists and
the one a reader cannot see in either document alone. And **the reader is held to
the writer**: `compare.py` parses documents `render.py` produces, so a key renamed
on one side and not the other would silently yield entries with nothing in them
rather than an error. `TestTheReaderMatchesTheWriter` is what fails instead.
"""

from __future__ import annotations

import json as json_lib

import pytest

from qedro import compare, config, quality, render, vocabulary
from qedro.errors import ConfigError, UsageError
from qedro.ropa import Provenance, build

from .test_quality import event as quality_event
from .test_ropa import EVIDENCED, event

WORDS = vocabulary.load()
CONTROLLER = "controller: ACME GmbH\n"


def rendered(events, cfg=CONTROLLER):
    """A real record, through the real renderer, as a real document."""
    record = build(events, config=config.parse(cfg), vocabulary=WORDS)
    return json_lib.loads(render.json(record))


def document(activities=(), declared=(), **scope):
    """A document assembled by hand, for the cases a full record cannot reach cheaply."""
    window = {
        "since": scope.pop("since", "2026-03-01T00:00:00+00:00"),
        "until": scope.pop("until", "2026-03-31T00:00:00+00:00"),
    }
    return {
        "qedro": {"schema": 1, "projection": "ropa", "view": "art30", "version": "0.4.0"},
        "activities": list(activities),
        "declared": list(declared),
        "scope": {"source": scope.pop("source", "demo/lineage"), "window": window, **scope},
        "complete": scope.pop("complete", True),
        "reasons": [],
    }


def activity(job="acme.fraud/scored", purpose="fraud-detection", provenance="facet", **kw):
    return {
        "job": job,
        "domain": kw.pop("domain", "fraud"),
        "domain_source": kw.pop("domain_source", "mapping"),
        "purpose": {"value": purpose, "provenance": provenance, "unrecognised": False},
        "legal_basis": {
            "value": kw.pop("legal_basis", "legitimate-interest"),
            "provenance": kw.pop("legal_basis_provenance", provenance),
            "unrecognised": False,
        },
        "reads": kw.pop("reads", ["wh/raw.customers"]),
        "writes": kw.pop("writes", ["wh/curated.scores"]),
        "recipients": {"values": kw.pop("recipients", []), "provenance": "mapping"},
        "security_measures": {"values": kw.pop("security_measures", []), "provenance": "mapping"},
        "classification": kw.pop("classification", []),
        **kw,
    }


def compared(before, after):
    return compare.compare(
        compare.side(before, origin="before"), compare.side(after, origin="after")
    )


class TestTheReaderMatchesTheWriter:
    """A document this tool wrote has to be one it can read back.

    `render.py` and `compare.py` are the two halves of the same contract, and a
    key renamed on one side alone would produce entries with empty fields rather
    than an error — a comparison that reports *nothing changed* about a record it
    failed to read is the worst answer available.
    """

    def test_a_rendered_record_reads_back_with_its_fields_intact(self):
        side = compare.side(rendered([event(facet=EVIDENCED)]), origin="x")
        [entry] = side.entries.values()
        assert entry.kind == "activity"
        assert entry.single["purpose"] == compare.Value("fraud-detection", Provenance.FACET)
        assert entry.single["legal basis"].value == "legitimate-interest"
        assert [v.value for v in entry.sets["reads"]] == ["wh/raw.customers"]
        assert [v.value for v in entry.sets["writes"]] == ["wh/curated.scores"]

    def test_the_document_block_is_read(self):
        side = compare.side(rendered([event(facet=EVIDENCED)]), origin="x")
        assert (side.schema, side.projection, side.view) == (render.SCHEMA, "ropa", "art30")
        assert side.shape == "ropa/art30"

    def test_the_verdict_and_its_reasons_are_read(self):
        side = compare.side(rendered([event()]), origin="x")
        assert side.complete is False
        assert side.reasons

    def test_classification_reads_back_under_its_vocabulary_key(self):
        from .test_ropa import tagged

        side = compare.side(
            rendered([tagged(writes=[("wh/scores", {"data_category": "contact"})])]), origin="x"
        )
        [entry] = side.entries.values()
        assert [v.value for v in entry.sets["classification.data_category"]] == ["contact"]

    def test_a_declared_activity_reads_back_as_declared(self):
        side = compare.side(
            document(
                declared=[
                    {
                        "name": "payroll-run",
                        "domain": "hr",
                        "purpose": {"value": "payroll", "provenance": "declared"},
                        "legal_basis": {"value": "legal-obligation", "provenance": "declared"},
                        "model": "",
                        "inputs_declared": ["employee master data"],
                        "recipients": {
                            "values": ["the payroll provider"],
                            "provenance": "declared",
                        },
                        "security_measures": {"values": [], "provenance": "declared"},
                        "note": "",
                    }
                ]
            ),
            origin="x",
        )
        entry = side.entries["payroll-run"]
        assert entry.kind == "declared"
        assert entry.single["purpose"].provenance is Provenance.DECLARED


class TestRefusals:
    """The one hard refusal is a difference of shape. Everything else is reported."""

    def test_two_different_projections_are_refused(self):
        ropa_side = compare.side(rendered([event(facet=EVIDENCED)]), origin="a")
        quality_side = compare.side(
            json_lib.loads(
                render.json(
                    quality.build(
                        [quality_event(reads="wh/unchecked")], config=config.parse(CONTROLLER)
                    )
                )
            ),
            origin="b",
        )
        with pytest.raises(UsageError, match="different documents"):
            compare.compare(ropa_side, quality_side)

    def test_the_art30_and_deployer_views_are_refused(self):
        # The same projection and not the same document. Comparing them would
        # report every AI-specific field as removed.
        art30 = document()
        deployer = document()
        deployer["qedro"] = dict(deployer["qedro"], view="deployer")
        with pytest.raises(UsageError, match="ropa/art30"):
            compared(art30, deployer)

    def test_a_projection_that_cannot_be_compared_yet_says_so(self):
        both = [document(), document()]
        for doc in both:
            doc["qedro"] = dict(doc["qedro"], projection="quality", view="")
        with pytest.raises(UsageError, match="cannot be compared yet"):
            compared(*both)

    def test_a_schema_from_the_future_is_refused_rather_than_guessed(self):
        newer = document()
        newer["qedro"] = dict(newer["qedro"], schema=99)
        with pytest.raises(UsageError, match="schema 99"):
            compared(document(), newer)

    def test_a_file_that_is_not_json_names_the_path(self, tmp_path):
        path = tmp_path / "not.json"
        path.write_text("{oh no")
        with pytest.raises(ConfigError, match="not.json is not JSON"):
            compare.read(str(path))

    def test_json_that_is_not_a_record_is_refused(self, tmp_path):
        path = tmp_path / "other.json"
        path.write_text('{"something": "else"}')
        with pytest.raises(ConfigError, match="does not look like a record"):
            compare.read(str(path))


class TestOlderDocuments:
    """0.1 to 0.3 are on PyPI and wrote no `qedro` block. Their output exists."""

    def test_a_document_with_no_block_is_schema_zero(self):
        old = document()
        del old["qedro"]
        side = compare.side(old, origin="old")
        assert (side.schema, side.projection, side.view) == (0, "ropa", "art30")

    def test_the_old_deployer_key_is_still_understood(self):
        old = document()
        del old["qedro"]
        old["view"] = "deployer"
        assert compare.side(old, origin="old").view == "deployer"

    def test_it_is_compared_with_the_difference_stated_rather_than_refused(self):
        old = document()
        del old["qedro"]
        result = compared(old, document())
        assert any(
            "before the document schema was numbered" in c for c in result.comparability.cautions()
        )


class TestComparability:
    """Stated before any finding, because coverage and processing look alike."""

    def test_identical_windows_and_one_source_are_like_for_like(self):
        result = compared(document(), document())
        assert result.comparability.overlap == "identical"
        assert result.comparability.like_for_like
        assert result.comparability.cautions() == ()

    @pytest.mark.parametrize(
        ("since", "until", "expected"),
        [
            ("2026-03-15T00:00:00+00:00", "2026-04-15T00:00:00+00:00", "overlapping"),
            ("2026-03-31T00:00:00+00:00", "2026-04-30T00:00:00+00:00", "adjacent"),
            ("2026-05-01T00:00:00+00:00", "2026-05-31T00:00:00+00:00", "disjoint"),
        ],
    )
    def test_how_the_windows_sit(self, since, until, expected):
        result = compared(document(), document(since=since, until=until))
        assert result.comparability.overlap == expected
        assert result.comparability.cautions()

    def test_an_open_window_is_unknown_rather_than_invented(self):
        result = compared(document(), document(since="", until=""))
        assert result.comparability.overlap == "unknown"

    def test_a_different_source_is_a_caution_not_a_refusal(self):
        result = compared(document(), document(source="s3://exports/lineage"))
        assert not result.comparability.same_source
        assert any("different sources" in c for c in result.comparability.cautions())

    def test_windows_of_different_length_are_named(self):
        result = compared(document(), document(until="2026-03-08T00:00:00+00:00"))
        assert result.comparability.same_length is False
        assert any("same length" in c for c in result.comparability.cautions())

    def test_both_verdicts_are_carried(self):
        result = compared(document(), document(complete=False))
        assert result.before.complete is True
        assert result.after.complete is False


class TestFindings:
    def test_an_activity_only_on_the_after_side_is_added(self):
        result = compared(document(), document([activity()]))
        [change] = result.changes
        assert (change.kind, change.entry) == (compare.ADDED, "acme.fraud/scored")
        assert not change.regression

    def test_an_activity_only_on_the_before_side_is_removed_and_is_a_regression(self):
        result = compared(document([activity()]), document())
        [change] = result.changes
        assert change.kind == compare.REMOVED
        assert change.regression

    def test_a_changed_value_is_reported_with_both(self):
        result = compared(document([activity()]), document([activity(purpose="marketing")]))
        [change] = [c for c in result.changes if c.field == "purpose"]
        assert change.kind == compare.CHANGED
        assert (change.before.value, change.after.value) == ("fraud-detection", "marketing")

    def test_the_same_value_from_a_weaker_source_is_a_regression(self):
        """The finding no single record can show."""
        result = compared(document([activity()]), document([activity(provenance="mapping")]))
        purpose = next(c for c in result.changes if c.field == "purpose")
        assert purpose.kind == compare.REGRESSED
        assert purpose.before.value == purpose.after.value == "fraud-detection"
        assert (purpose.before.provenance, purpose.after.provenance) == (
            Provenance.FACET,
            Provenance.MAPPING,
        )
        assert purpose.regression

    def test_the_same_value_from_a_stronger_source_is_a_repair(self):
        result = compared(document([activity(provenance="mapping")]), document([activity()]))
        purpose = next(c for c in result.changes if c.field == "purpose")
        assert purpose.kind == compare.REPAIRED
        assert not purpose.regression

    def test_a_value_that_stopped_being_stated_is_a_regression_even_though_it_changed(self):
        # `changed` because the value moved as well, and the worst of these
        # findings rather than an ordinary one, so provenance decides.
        result = compared(
            document([activity()]), document([activity(purpose="", provenance="absent")])
        )
        purpose = next(c for c in result.changes if c.field == "purpose")
        assert purpose.kind == compare.CHANGED
        assert purpose.regression
        assert str(purpose.after) == "nothing"

    def test_a_dataset_appearing_is_gained_and_the_rest_stay_put(self):
        result = compared(
            document([activity()]),
            document([activity(reads=["wh/raw.customers", "wh/raw.devices"])]),
        )
        [change] = result.changes
        assert (change.kind, change.field) == (compare.GAINED, "reads")
        assert change.after.value == "wh/raw.devices"

    def test_a_dataset_disappearing_is_lost(self):
        result = compared(document([activity()]), document([activity(reads=[])]))
        [change] = result.changes
        assert change.kind == compare.LOST
        assert change.regression

    def test_a_recipient_added_is_a_finding_about_art30_1_d(self):
        result = compared(
            document([activity()]), document([activity(recipients=["the card scheme"])])
        )
        [change] = result.changes
        assert (change.kind, change.field) == (compare.GAINED, "recipients")

    def test_a_classification_change_names_the_vocabulary_term(self):
        before = activity(
            classification=[{"key": "data_category", "value": "contact", "provenance": "facet"}]
        )
        after = activity(
            classification=[
                {"key": "data_category", "value": "contact", "provenance": "facet"},
                {"key": "special_category", "value": "health", "provenance": "facet"},
            ]
        )
        result = compared(document([before]), document([after]))
        [change] = result.changes
        assert change.field == "classification.special_category"
        # The prefix keeps a vocabulary term named `reads` from colliding with
        # the dataset list; a reader should never see it.
        assert change.label == "special_category"

    def test_a_domain_that_stopped_being_mapped_is_a_regression(self):
        # Same domain, decided by a guess instead of a rule. See #9.
        result = compared(document([activity()]), document([activity(domain_source="namespace")]))
        [change] = result.changes
        assert (change.field, change.kind) == ("domain", compare.REGRESSED)

    def test_an_untouched_activity_is_counted_rather_than_listed(self):
        result = compared(document([activity()]), document([activity()]))
        assert result.changes == ()
        assert result.unchanged == 1

    def test_findings_are_grouped_under_the_activity_they_are_about(self):
        result = compared(
            document([activity(), activity(job="acme.crm/sync")]),
            document([activity(purpose="marketing"), activity(job="acme.crm/sync", reads=[])]),
        )
        assert [key for key, _ in result.by_entry()] == ["acme.crm/sync", "acme.fraud/scored"]

    def test_volume_is_not_compared(self):
        """Runs, events and timestamps differ between any two windows.

        Reporting them would bury the findings that matter under arithmetic, and
        both numbers are already in the two scope statements.
        """
        result = compared(
            document([activity(runs=3, events=6, last_seen="2026-03-02T10:00:00+00:00")]),
            document([activity(runs=9, events=18, last_seen="2026-03-29T10:00:00+00:00")]),
        )
        assert result.changes == ()
        assert result.unchanged == 1


class TestTheComparisonsOwnScope:
    """#3: the scope statement is unconditional, and this one is the comparison's."""

    def test_it_states_what_a_comparison_cannot_verify(self):
        result = compared(document(), document())
        assert "verifies neither" in result.scope.OUT_OF_VIEW
        assert "unchanged is not the same as correct" in result.scope.OUT_OF_VIEW

    def test_it_names_both_documents_and_the_window_of_each(self):
        result = compared(document(), document())
        rows = dict(result.scope.lines())
        assert rows["before"].startswith("before — 2026-03-01")
        assert rows["after"].startswith("after — 2026-03-01")

    def test_its_window_spans_both(self):
        result = compared(document(), document(until="2026-04-30T00:00:00+00:00"))
        assert result.scope.since.isoformat().startswith("2026-03-01")
        assert result.scope.until.isoformat().startswith("2026-04-30")

    def test_two_versions_of_the_tool_are_named_when_they_differ(self):
        newer = document()
        newer["qedro"] = dict(newer["qedro"], version="0.5.0")
        rows = dict(compared(document(), newer).scope.lines())
        assert rows["written by"] == "qedro 0.4.0 / qedro 0.5.0"


class TestTheDemoEstate:
    """The acceptance case in #14: the two estates differ only by the facet."""

    @staticmethod
    def estates():
        import subprocess
        import sys

        out = []
        for name in ("lineage-declared", "lineage"):
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "qedro",
                    "ropa",
                    f"demo/{name}",
                    "--config",
                    "demo/qedro.yaml",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            out.append(json_lib.loads(result.stdout))
        return out

    def test_every_mapped_activity_regressed_from_facet_to_mapping(self):
        before, after = self.estates()
        result = compared(before, after)
        regressed = {
            c.entry
            for c in result.changes
            if c.before
            and c.after
            and c.before.provenance is Provenance.FACET
            and c.after.provenance is Provenance.MAPPING
        }
        assert regressed == {
            "acme.billing/dunning-weekly",
            "acme.billing/invoices-nightly",
            "acme.crm/customers-curated",
            "acme.fraud/scores-validated",
            "acme.fraud/transactions-scored-daily",
        }

    def test_the_job_no_rule_matches_loses_its_purpose_altogether(self):
        # `acme.crm/consent-sync` matches no pattern in demo/qedro.yaml, which
        # is the demo's point: a register maintained by hand has holes.
        before, after = self.estates()
        result = compared(before, after)
        purpose = next(
            c for c in result.changes if c.entry == "acme.crm/consent-sync" and c.field == "purpose"
        )
        assert purpose.after.value == ""
        assert purpose.regression

    def test_every_finding_is_a_regression_and_the_verdict_moved_with_them(self):
        before, after = self.estates()
        result = compared(before, after)
        assert result.changes
        assert result.regressions == result.changes
        assert (result.before.complete, result.after.complete) == (True, False)
