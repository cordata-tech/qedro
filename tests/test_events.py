"""Parsing, with the awkward cases the spec does not promise won't happen.

Most of these are about tolerance rather than correctness. A directory of
production lineage holds events from emitters that disagree with each other,
and the parser's contract is that it never raises and never silently invents
a value it did not receive.
"""

from datetime import datetime

from qedro.events import Dataset, parse_event


def _event(**over):
    base = {
        "eventType": "COMPLETE",
        "eventTime": "2026-08-21T10:00:00Z",
        "run": {"runId": "r-1", "facets": {}},
        "job": {"namespace": "ns", "name": "job", "facets": {}},
        "inputs": [],
        "outputs": [],
    }
    base.update(over)
    return base


class TestWhatMakesAnEventUsable:
    def test_a_well_formed_event_parses(self):
        e = parse_event(_event())
        assert e is not None
        assert e.event_type == "COMPLETE"
        assert e.job.key == "ns/job"

    def test_no_job_means_unusable(self):
        # Without a job there is nothing to attribute the work to, so the
        # event cannot appear in any projection.
        assert parse_event(_event(job={"namespace": "ns"})) is None
        assert parse_event({"eventType": "COMPLETE"}) is None

    def test_no_event_type_means_unusable(self):
        raw = _event()
        del raw["eventType"]
        assert parse_event(raw) is None

    def test_a_missing_run_id_is_tolerated(self):
        # Some emitters omit it on OTHER events. The event is still evidence
        # that a job existed and touched datasets.
        e = parse_event(_event(run={}))
        assert e is not None
        assert e.run.run_id == ""

    def test_junk_never_raises(self):
        for junk in (None, 42, "a string", [], {"nothing": "useful"}):
            assert parse_event(junk) is None

    def test_an_unknown_event_type_is_passed_through(self):
        # The spec has gained event types before. A reader that rejects
        # unknown ones breaks on somebody else's upgrade rather than its own.
        e = parse_event(_event(eventType="SOMETHING_NEW"))
        assert e is not None
        assert e.event_type == "SOMETHING_NEW"

    def test_event_type_is_normalised_to_upper(self):
        assert parse_event(_event(eventType="complete")).event_type == "COMPLETE"


class TestTime:
    def test_z_suffix_and_offsets_both_parse(self):
        assert parse_event(
            _event(eventTime="2026-08-21T10:00:00Z")
        ).event_time == datetime.fromisoformat("2026-08-21T10:00:00+00:00")

    def test_an_unparseable_time_is_none_rather_than_a_guess(self):
        # None is honest and a projection filtering by date can say so. A
        # fabricated instant would be silently wrong in an audit artefact.
        assert parse_event(_event(eventTime="last Tuesday")).event_time is None
        assert parse_event(_event(eventTime=1755772800)).event_time is None


class TestDatasets:
    def test_a_dataset_without_identity_is_dropped(self):
        # It cannot be joined to anything, so carrying it forward would only
        # inflate counts.
        e = parse_event(
            _event(inputs=[{"name": "has-no-namespace"}, {"namespace": "ns", "name": "ok"}])
        )
        assert [d.key for d in e.inputs] == ["ns/ok"]

    def test_inputs_and_outputs_are_reachable_together(self):
        e = parse_event(
            _event(
                inputs=[{"namespace": "ns", "name": "in"}],
                outputs=[{"namespace": "ns", "name": "out"}],
            )
        )
        assert [d.key for d in e.datasets] == ["ns/in", "ns/out"]

    def test_field_names_come_from_the_schema_facet(self):
        d = Dataset("ns", "t", {"schema": {"fields": [{"name": "a"}, {"name": "b"}]}})
        assert d.field_names() == ["a", "b"]

    def test_no_schema_facet_reports_nothing_rather_than_no_columns(self):
        assert Dataset("ns", "t").field_names() == []

    def test_malformed_field_entries_are_skipped_not_fatal(self):
        d = Dataset("ns", "t", {"schema": {"fields": [{"name": "a"}, "junk", {"no": "name"}]}})
        assert d.field_names() == ["a"]


class TestFacets:
    def test_bookkeeping_keys_are_stripped(self):
        # _producer and _schemaURL are on every facet and are noise to a
        # caller that asked for the payload.
        e = parse_event(
            _event(
                job={
                    "namespace": "ns",
                    "name": "j",
                    "facets": {"processing": {"_producer": "x", "purpose": "fraud"}},
                }
            )
        )
        assert e.job_facet("processing") == {"purpose": "fraud"}

    def test_an_absent_facet_is_none(self):
        assert parse_event(_event()).job_facet("processing") is None

    def test_a_facet_that_is_not_a_mapping_is_none(self):
        e = parse_event(
            _event(job={"namespace": "ns", "name": "j", "facets": {"processing": "nope"}})
        )
        assert e.job_facet("processing") is None

    def test_the_raw_event_survives_for_facets_nobody_modelled(self):
        raw = _event()
        assert parse_event(raw).raw is raw
