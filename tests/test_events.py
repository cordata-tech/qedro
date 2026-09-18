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


class TestTheDatasetKey:
    """Namespace and name joined, without the double slash #23 found."""

    def key(self, namespace, name):
        return Dataset(namespace=namespace, name=name).key

    def test_a_uri_namespace_and_a_relative_name_are_unchanged(self):
        assert self.key("s3://bucket", "raw/orders.csv") == "s3://bucket/raw/orders.csv"
        assert self.key("postgres://db:5432", "shop.public.orders") == (
            "postgres://db:5432/shop.public.orders"
        )
        assert self.key("warehouse", "fraud_curated.scores") == "warehouse/fraud_curated.scores"

    def test_an_absolute_path_is_not_given_a_second_slash(self):
        assert self.key("hdfs://nn:8020", "/warehouse/orders") == "hdfs://nn:8020/warehouse/orders"
        assert self.key("file://host", "/data/orders.csv") == "file://host/data/orders.csv"

    def test_the_bare_file_namespace_is_written_as_the_spec_s_uri(self):
        # Airflow's provider and the Spark integration emit `file`; the naming
        # conventions give `file://{host}`, here with an empty host.
        assert self.key("file", "/data/raw/orders.csv") == "file:///data/raw/orders.csv"

    def test_file_and_file_with_an_empty_host_are_the_same_dataset(self):
        assert self.key("file", "/data/x") == self.key("file://", "/data/x")

    def test_only_the_legacy_key_keeps_the_old_spelling(self):
        dataset = Dataset(namespace="file", name="/data/x")
        assert dataset.legacy_key == "file//data/x"


class TestTheTagsDatasetFacet:
    """Classification from the standard `tags` dataset facet. See #13.

    No integration emitted this facet as of openlineage 1.53.0, so the absent
    case is the common one and has to mean *nothing reported it*.
    """

    def dataset(self, tags):
        return Dataset(namespace="wh", name="customers", facets={"tags": {"tags": tags}})

    def test_key_value_source_and_field_are_read(self):
        [tag] = self.dataset(
            [{"key": "data_category", "value": "health", "source": "CATALOG", "field": "diagnosis"}]
        ).tags()
        assert (tag.key, tag.value, tag.source, tag.field) == (
            "data_category",
            "health",
            "CATALOG",
            "diagnosis",
        )
        assert tag.column

    def test_a_tag_about_the_whole_dataset_names_no_column(self):
        [tag] = self.dataset([{"key": "residency", "value": "eu"}]).tags()
        assert tag.field == ""
        assert not tag.column

    def test_an_entry_missing_key_or_value_is_dropped_not_fatal(self):
        # The spec requires both, and a tag missing either cannot be resolved
        # against a vocabulary. Dropped, like every other malformed input here.
        tags = self.dataset(
            [
                {"key": "data_category"},
                {"value": "health"},
                {"key": "", "value": "health"},
                {"key": "residency", "value": "eu"},
                "not a mapping",
            ]
        ).tags()
        assert [t.key for t in tags] == ["residency"]

    def test_no_facet_reports_nothing_rather_than_no_classification(self):
        assert Dataset(namespace="wh", name="customers").tags() == ()

    def test_a_facet_that_is_not_a_list_is_not_fatal(self):
        assert self.dataset("everything").tags() == ()
