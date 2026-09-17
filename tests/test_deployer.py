"""The deployer view of the Art. 30 record.

Four properties carry this view, and each is tested against the failure it
exists to prevent:

**It is a view of the record, not a restatement.** A use case holds the Art. 30
record's own activity, so the two cannot disagree about purpose or legal basis.
Tested by identity, not by equal strings — equal strings are what two
independent implementations would also produce, until the day they did not.

**The model version is read, not assumed**, from the two documented places, and
runs that reported none are counted rather than smoothed over.

**Retention is a span, never a verdict.** A short span is stated and does not
withhold the mark, because withholding it would imply Art. 26(6) applies today.

**Declared use cases are assertions.** They are marked in the record and withhold
the mark.
"""

from __future__ import annotations

import pytest

from qedro import config, declared, deployer, ropa, vocabulary
from qedro.errors import ConfigError
from qedro.events import parse_event
from qedro.ropa import Provenance
from qedro.sources import ReadReport

WORDS = vocabulary.load()
CONTROLLER = "controller: ACME GmbH\n"
EVIDENCED = {"purpose": "fraud-detection", "legal_basis": "legitimate-interest"}


def event(
    name="scored",
    namespace="acme.fraud",
    run="r1",
    when="2026-03-01T10:00:00Z",
    model=None,
    model_via="tags",
    facet=None,
    reads=("raw.transactions",),
    event_type="COMPLETE",
):
    """One event, reporting a model version the way the named facet does."""
    run_facets = {}
    if model is not None and model_via == "tags":
        run_facets["tags"] = {
            "_producer": "https://example.test",
            "tags": [
                {"key": "openlineage_client_version", "value": "1.52.0"},
                {"key": "model_version", "value": model, "source": "USER"},
            ],
        }
    elif model is not None and model_via == "cordata_provenance":
        run_facets["cordata_provenance"] = {
            "_producer": "https://example.test",
            "step_params": {"score": {"model_version": model}},
        }

    raw = {
        "eventType": event_type,
        "eventTime": when,
        "run": {"runId": run, "facets": run_facets},
        "job": {"namespace": namespace, "name": name, "facets": {}},
        "inputs": [{"namespace": "wh", "name": n} for n in reads],
    }
    if facet:
        raw["job"]["facets"]["processing"] = facet
    parsed = parse_event(raw)
    assert parsed is not None
    return parsed


def view(events, *, cfg="", declared_uses=(), report=None, since=None, until=None):
    if "controller" not in cfg:
        cfg = CONTROLLER + cfg
    settings = config.parse(cfg)
    record = ropa.build(
        events, config=settings, vocabulary=WORDS, report=report, declared=declared_uses
    )
    return record, deployer.build(record, events, report=report, since=since, until=until)


def a_declared(**overrides):
    spec = {
        "purpose": "customer-support",
        "legal_basis": "contract",
        "domain": "crm",
        "model": "vendor assistant",
        "inputs": ["customer emails"],
        "note": "pasted into the vendor UI",
    }
    spec.update(overrides)
    return declared.parse(
        {"activities": {"support-reply-drafts": spec}}, origin="test", vocabulary=WORDS
    )


class TestAViewOfTheRecordNotARestatement:
    def test_a_use_case_holds_the_record_s_own_activity(self):
        record, out = view([event(model="v1", facet=EVIDENCED)])
        [use_case] = out.use_cases
        [activity] = record.activities
        assert use_case.activity is activity

    def test_so_purpose_and_basis_carry_the_record_s_provenance(self):
        cfg = 'jobs:\n  "*": {purpose: p, legal_basis: consent}\n'
        record, out = view([event(model="v1")], cfg=cfg)
        [use_case] = out.use_cases
        assert use_case.activity.purpose is record.activities[0].purpose
        assert use_case.activity.purpose.provenance is Provenance.MAPPING

    def test_an_activity_that_ran_no_model_is_counted_not_listed(self):
        events = [
            event(name="scored", run="r1", model="v1", facet=EVIDENCED),
            event(name="loaded", run="r2", facet=EVIDENCED),
        ]
        _, out = view(events)
        assert [u.key for u in out.use_cases] == ["acme.fraud/scored"]
        assert out.scope.activities == 2
        assert out.scope.use_cases == 1


class TestTheModelVersionIsRead:
    def test_from_the_standard_tags_facet(self):
        _, out = view([event(model="2026-06-fraud-v3", facet=EVIDENCED)])
        [model] = out.use_cases[0].models
        assert model.version == "2026-06-fraud-v3"
        assert model.reported_by == "tags"

    def test_from_pipeline_runtime_s_step_params(self):
        # Where `pipeline-runtime` puts it — checked against an emitted event,
        # docs/evidence/fraud-event.trimmed.json.
        _, out = view([event(model="2026-07-fraud-v3", model_via="cordata_provenance")])
        [model] = out.use_cases[0].models
        assert model.version == "2026-07-fraud-v3"
        assert model.reported_by == "cordata_provenance"

    def test_from_the_real_captured_event(self):
        from pathlib import Path

        from qedro.sources import read_dir

        events, _ = read_dir(Path("docs/evidence/fraud-events.captured.ndjson"))
        record = ropa.build(events, config=config.parse(CONTROLLER), vocabulary=WORDS)
        out = deployer.build(record, events)
        [use_case] = out.use_cases
        assert use_case.key == "cordata.fraud/transactions-scored-daily"
        assert use_case.models[0].version == "2026-07-fraud-v3"
        assert use_case.activity.purpose.value == "fraud-detection"
        assert use_case.activity.purpose.evidenced

    def test_versions_are_counted_per_run_and_dated(self):
        events = [
            event(run=f"r{n}", when=f"2026-03-0{n}T10:00:00Z", model="v1", facet=EVIDENCED)
            for n in (1, 2)
        ] + [event(run="r3", when="2026-03-05T10:00:00Z", model="v2", facet=EVIDENCED)]
        _, out = view(events)
        [newest, older] = out.use_cases[0].models
        assert (newest.version, newest.runs) == ("v2", 1)
        assert (older.version, older.runs) == ("v1", 2)
        assert str(older.last_seen.date()) == "2026-03-02"

    def test_a_start_and_complete_of_one_run_are_one_run(self):
        events = [
            event(run="r1", event_type="START", model="v1", facet=EVIDENCED),
            event(run="r1", event_type="COMPLETE", model="v1", facet=EVIDENCED),
        ]
        _, out = view(events)
        assert out.use_cases[0].models[0].runs == 1

    def test_runs_that_reported_no_version_are_counted_and_withhold_the_mark(self):
        events = [
            event(run="r1", when="2026-03-01T10:00:00Z", model="v1", facet=EVIDENCED),
            event(run="r2", when="2026-03-02T10:00:00Z", facet=EVIDENCED),
        ]
        _, out = view(events)
        assert out.use_cases[0].runs_without_model == 1
        assert not out.complete
        assert any("reported no model version" in r for r in out.completeness.reasons)


class TestTheLatestRun:
    def test_names_the_inputs_that_run_read_and_its_model(self):
        events = [
            event(run="r1", when="2026-03-01T10:00:00Z", model="v1", reads=("old",)),
            event(run="r2", when="2026-03-02T10:00:00Z", model="v2", reads=("new", "other")),
        ]
        _, out = view(events)
        latest = out.use_cases[0].latest
        assert latest.run_id == "r2"
        assert latest.model_version == "v2"
        assert latest.inputs == ("wh/new", "wh/other")


class TestRetentionIsASpanNeverAVerdict:
    def test_the_span_of_run_records_is_reported(self):
        events = [
            event(run="r1", when="2026-03-01T10:00:00Z", model="v1", facet=EVIDENCED),
            event(run="r2", when="2026-03-21T10:00:00Z", model="v1", facet=EVIDENCED),
        ]
        _, out = view(events)
        assert out.use_cases[0].span_days == 20

    def test_a_short_span_does_not_withhold_the_mark(self):
        # Withholding for it would imply Art. 26(6) applies today. It applies to
        # Annex III high-risk systems from 2 December 2027.
        _, out = view([event(model="v1", facet=EVIDENCED)])
        assert out.use_cases[0].span_days == 0
        assert out.complete

    def test_a_window_on_the_query_is_said_to_bound_the_query_not_retention(self):
        from datetime import UTC, datetime

        _, out = view([event(model="v1", facet=EVIDENCED)], since=datetime(2026, 3, 1, tzinfo=UTC))
        assert out.scope.windowed
        assert any(label == "retention" for label, _ in out.scope.lines())

    def test_no_retention_policy_is_ever_claimed(self):
        assert "not the source's retention policy" in deployer.Scope.OUT_OF_VIEW


class TestTheLawIsCitedWithItsCondition:
    def test_the_consolidated_text_is_cited(self):
        _, out = view([event(model="v1", facet=EVIDENCED)])
        assert "CELEX 02024R1689-20260727" in out.regulation

    def test_art_26_carries_its_date_and_its_scope(self):
        _, out = view([event(model="v1", facet=EVIDENCED)])
        assert "2 December 2027" in out.application
        assert "Annex III" in out.application
        assert "not decided" in out.application


class TestDeclaredUseCases:
    def test_they_are_marked_declared_not_evidenced(self):
        [entry] = a_declared()
        assert entry.purpose.provenance is Provenance.DECLARED
        assert not entry.purpose.evidenced

    def test_they_withhold_the_mark(self):
        _, out = view([event(model="v1", facet=EVIDENCED)], declared_uses=a_declared())
        assert not out.complete
        assert any("declared rather than evidenced" in r for r in out.completeness.reasons)

    def test_they_are_counted_apart_from_use_cases_from_lineage(self):
        _, out = view([event(model="v1", facet=EVIDENCED)], declared_uses=a_declared())
        assert out.scope.use_cases == 1
        assert out.scope.declared == 1

    def test_a_view_of_nothing_but_declared_use_cases_says_why_it_is_no_proof(self):
        _, out = view([event(facet=EVIDENCED)], declared_uses=a_declared())
        assert out.use_cases == ()
        assert [r for r in out.completeness.reasons if "declared" in r]

    def test_a_value_outside_the_vocabulary_is_flagged(self):
        [entry] = a_declared(legal_basis="vibes")
        assert entry.legal_basis.unrecognised

    def test_an_unknown_key_is_a_sentence_not_a_silent_drop(self):
        with pytest.raises(ConfigError, match="unknown keys legalbasis"):
            a_declared(legalbasis="contract")

    def test_a_document_without_activities_is_refused(self):
        with pytest.raises(ConfigError, match="no `activities:`"):
            declared.parse({"jobs": {}}, origin="test", vocabulary=WORDS)

    def test_inputs_must_be_strings(self):
        with pytest.raises(ConfigError, match="list of strings"):
            a_declared(inputs=[1, 2])

    def test_read_from_a_file_in_any_of_the_three_formats(self, tmp_path):
        path = tmp_path / "activities.toml"
        path.write_text(
            '[activities.drafts]\npurpose = "customer-support"\nlegal_basis = "contract"\n',
            encoding="utf-8",
        )
        [entry] = declared.load(path, vocabulary=WORDS)
        assert entry.name == "drafts"
        assert entry.legal_basis.value == "contract"


class TestTheMark:
    def test_earned_when_every_use_case_stands_on_emitted_evidence(self):
        _, out = view([event(model="v1", facet=EVIDENCED)])
        assert out.complete
        assert out.completeness.reasons == ()

    def test_withheld_when_purpose_comes_from_the_mapping_file(self):
        cfg = 'jobs:\n  "*": {purpose: p, legal_basis: consent}\n'
        _, out = view([event(model="v1")], cfg=cfg)
        assert any("mapping file" in r for r in out.completeness.reasons)

    def test_withheld_when_nothing_is_declared_at_all(self):
        _, out = view([event(model="v1")])
        assert any("no purpose or no legal basis" in r for r in out.completeness.reasons)

    def test_withheld_when_no_use_case_was_found(self):
        _, out = view([event(facet=EVIDENCED)])
        assert any("no AI use cases were found" in r for r in out.completeness.reasons)

    def test_withheld_when_the_read_was_degraded(self):
        report = ReadReport(origin="./x", events=1, skipped_records=1)
        _, out = view([event(model="v1", facet=EVIDENCED)], report=report)
        assert not out.complete

    def test_withheld_without_a_controller(self):
        record = ropa.build(
            [event(model="v1", facet=EVIDENCED)], config=config.Config(), vocabulary=WORDS
        )
        out = deployer.build(record, [event(model="v1", facet=EVIDENCED)])
        assert any("no controller" in r for r in out.completeness.reasons)


class TestTheReasonsReadLikeSentences:
    """Found in the first captured transcript: "1 of 1 use case takes purpose or
    legal basis from the mapping file ... so those entries are asserted"."""

    def test_one_mapped_use_case_is_that_entry(self):
        cfg = 'jobs:\n  "*": {purpose: p, legal_basis: consent}\n'
        _, out = view([event(model="v1")], cfg=cfg)
        [reason] = [r for r in out.completeness.reasons if "mapping file" in r]
        assert "1 of 1 use case takes" in reason
        assert "that entry is asserted" in reason

    def test_two_mapped_use_cases_are_those_entries(self):
        cfg = 'jobs:\n  "*": {purpose: p, legal_basis: consent}\n'
        events = [event(name="a", run="r1", model="v1"), event(name="b", run="r2", model="v1")]
        _, out = view(events, cfg=cfg)
        [reason] = [r for r in out.completeness.reasons if "mapping file" in r]
        assert "2 of 2 use cases take" in reason
        assert "those entries are asserted" in reason


class TestOnlyDeclaredAIUsesAreUseCases:
    """A declared payroll SaaS is an Art. 30 activity and not an AI use case.

    The same rule as for lineage: a job whose runs reported no model version is
    in the record and not in this view.
    """

    def test_a_declared_activity_without_a_model_is_not_listed(self):
        record, out = view([event(model="v1", facet=EVIDENCED)], declared_uses=a_declared(model=""))
        assert len(record.declared) == 1
        assert out.declared == ()
        assert out.scope.declared == 0

    def test_and_does_not_withhold_this_view_s_mark(self):
        # It withholds the Art. 30 record's mark, which is where it belongs.
        record, out = view([event(model="v1", facet=EVIDENCED)], declared_uses=a_declared(model=""))
        assert out.complete
        assert not record.complete
