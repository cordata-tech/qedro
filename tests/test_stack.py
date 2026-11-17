"""Where a step ran and where its data lives, as the events say (#39).

The rule under test is the one every other module here keeps: a label states
what an event said, and an event that said nothing gives no label, never a
guess from a name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qedro import config, stack
from qedro.errors import ConfigError
from qedro.events import parse_event
from qedro.sources import read

FIXTURES = Path(__file__).parent / "fixtures"


def event(*, integration=None, producer="https://example.test", namespace="wh", source=None):
    facets = {"jobType": {"integration": integration}} if integration else {}
    output = {"namespace": namespace, "name": "orders"}
    if source:
        output["facets"] = {"dataSource": {"name": "db", "uri": source}}
    parsed = parse_event(
        {
            "eventType": "COMPLETE",
            "eventTime": "2026-07-01T10:00:00+00:00",
            "producer": producer,
            "run": {"runId": "r"},
            "job": {"namespace": "acme", "name": "load", "facets": facets},
            "outputs": [output],
        }
    )
    assert parsed is not None
    return parsed


class TestWhatRanTheStep:
    def test_the_job_type_facet_names_it(self):
        assert stack.ran_on(event(integration="DBT")) == "dbt"

    def test_the_producer_is_read_when_the_facet_is_absent(self):
        producer = "https://github.com/OpenLineage/OpenLineage/tree/1.53.0/integration/spark"
        assert stack.ran_on(event(producer=producer)) == "Spark"

    def test_an_integration_nobody_labelled_is_printed_as_given(self):
        # The facet exists to name the integration, so an unfamiliar one is
        # still a statement about what ran.
        assert stack.ran_on(event(integration="PREFECT")) == "PREFECT"

    def test_an_event_that_names_nothing_gives_nothing(self):
        assert stack.ran_on(event()) == ""


class TestWhereTheDataLives:
    @pytest.mark.parametrize(
        ("namespace", "label"),
        [
            ("snowflake://acme.eu-central-1", "Snowflake"),
            ("s3://acme-exports", "S3"),
            ("postgres://db:5432", "PostgreSQL"),
            ("bigquery", "BigQuery"),
            ("file", "local files"),
        ],
    )
    def test_the_namespace_names_it(self, namespace, label):
        [output] = event(namespace=namespace).outputs
        assert stack.stored_in(output) == label

    def test_the_data_source_is_read_when_the_namespace_is_logical(self):
        [output] = event(namespace="warehouse", source="jdbc:snowflake://acme").outputs
        assert stack.stored_in(output) == "Snowflake"

    def test_an_unknown_scheme_is_not_taken_for_a_platform(self):
        # pipeline-runtime's `cordata://fraud` names a domain, not a platform.
        [output] = event(namespace="cordata://fraud").outputs
        assert stack.stored_in(output) == ""

    def test_platforms_in_the_config_label_one(self):
        labels = stack.labels(config.parse("platforms:\n  cordata: Glue catalog\n").platforms)
        [output] = event(namespace="cordata://fraud").outputs
        assert stack.stored_in(output, labels) == "Glue catalog"

    def test_platforms_in_the_config_replace_a_default(self):
        labels = stack.labels({"S3": "the export bucket"})
        [output] = event(namespace="s3://acme-exports").outputs
        assert stack.stored_in(output, labels) == "the export bucket"


class TestTheConfig:
    def test_a_label_must_be_words(self):
        with pytest.raises(ConfigError, match="platforms: s3"):
            config.parse("platforms:\n  s3: 3\n")

    def test_platforms_must_be_a_mapping(self):
        with pytest.raises(ConfigError, match="`platforms`"):
            config.parse("platforms: [s3]\n")


class TestTheStackOfADataset:
    def test_both_sides_join_with_a_dot(self):
        found = stack.of(
            [event(integration="DBT", namespace="snowflake://acme")], "snowflake://acme/orders"
        )
        assert found.describe() == "dbt · Snowflake"

    def test_nothing_known_is_an_empty_stack(self):
        found = stack.of([event()], "wh/orders")
        assert not found and found.describe() == ""


class TestRealCaptures:
    """What the stack reads from lineage real emitters produced."""

    @pytest.mark.parametrize(
        ("fixture", "expected"),
        [
            ("dbt-1.53", {"dbt · DuckDB"}),
            ("spark-4.2.0", {"Spark · local files"}),
            ("airflow-3.3.1", {"Airflow · local files"}),
            # Logical namespaces and no jobType facet: nothing to say.
            ("pipeline-runtime-0.2.5-checkout", {""}),
        ],
    )
    def test_each_says_what_its_events_carry(self, fixture, expected):
        events, _ = read(str(FIXTURES / fixture))
        written = {o.key for e in events for o in e.outputs}
        assert {stack.of(events, key).describe() for key in written} == expected


class TestKinds:
    """What a diagram draws an icon for: a kind of thing, never a vendor."""

    def test_each_label_has_the_kind_of_thing_it_is(self):
        found = stack.of(
            [event(integration="DBT", namespace="snowflake://acme")], "snowflake://acme/orders"
        )
        assert (found.ran_on_kind, found.stored_in_kind) == ("transformation", "database")

    def test_two_vendors_of_one_kind_share_it(self):
        assert stack.KINDS["Snowflake"] == stack.KINDS["PostgreSQL"] == "database"

    def test_a_label_with_no_kind_gets_no_icon(self):
        found = stack.of([event(integration="PREFECT")], "wh/orders")
        assert found.ran_on == "PREFECT" and found.ran_on_kind == ""

    def test_the_config_can_give_a_platform_its_kind(self):
        cfg = config.parse("platforms:\n  cordata:\n    label: AWS Glue\n    kind: database\n")
        found = stack.of(
            [event(namespace="cordata://fraud")],
            "cordata://fraud/orders",
            stack.labels(cfg.platforms),
            stack.kinds(cfg.platform_kinds),
        )
        assert (found.stored_in, found.stored_in_kind) == ("AWS Glue", "database")

    def test_a_kind_outside_the_list_is_refused_by_name(self):
        with pytest.raises(ConfigError, match="Allowed: database"):
            config.parse("platforms:\n  cordata:\n    label: AWS Glue\n    kind: lake\n")


class TestTheDiagram:
    """The tree draws the platform apart from the state, and explains its icons."""

    def nodes(self):
        from qedro import erasure
        from qedro.pdf import _erasure_nodes

        events, report = read("docs/examples/erasure")
        record = erasure.build(
            events,
            dataset="warehouse/crm_raw.contacts",
            config=config.parse("controller: ACME\n"),
            report=report,
        )
        return _erasure_nodes(record)

    def test_the_platform_is_its_own_line_not_one_of_the_states(self):
        by_key = {n.key: n for n in self.nodes()}
        customers = by_key["warehouse/crm_curated.customers"]
        assert customers.platform == "on dbt · Snowflake"
        assert all("Snowflake" not in line for line in customers.lines)

    def test_the_legend_names_only_the_kinds_the_tree_uses(self):
        from qedro.pdf import _legend

        legend = _legend(self.nodes())
        words = {s.text for s in legend.contents[0].contents if hasattr(s, "text")}
        assert words == {
            "database", "object storage", "transformation", "orchestrator", "processing engine",
        }  # fmt: skip

    def test_a_tree_with_no_kinds_has_no_legend(self):
        from qedro.pdf import _legend, _Node

        assert _legend([_Node("a", 0, ("a",), root=True)]) is None


class TestTheArt30Record:
    """The Art. 30 JSON says what ran each activity and where each dataset lives,
    so the console can draw the same kinds the PDF trees do (#39)."""

    def record(self):
        from qedro import ropa, vocabulary

        events, report = read("demo/lineage-declared")
        return ropa.build(
            events,
            config=config.load("demo/qedro.yaml"),
            vocabulary=vocabulary.load(),
            report=report,
        )

    def test_every_activity_names_what_ran_it(self):
        ran = {a.key: (a.stack.ran_on, a.stack.ran_on_kind) for a in self.record().activities}
        assert ran["acme.crm/customers-curated"] == ("dbt", "transformation")
        assert ran["acme.billing/invoices-nightly"] == ("Airflow", "orchestrator")
        assert set(ran.values()) <= {
            ("dbt", "transformation"),
            ("Airflow", "orchestrator"),
            ("Spark", "processing engine"),
        }

    def test_every_dataset_in_view_has_an_entry(self):
        record = self.record()
        in_view = {d for a in record.activities for d in (*a.inputs, *a.outputs)}
        assert set(record.stores) == in_view
        assert set(record.stores.values()) == {("PostgreSQL", "database")}

    def test_the_json_carries_both(self):
        import json

        from qedro import render

        payload = json.loads(render.json(self.record()))
        assert payload["activities"][0]["ran_on_kind"] in {
            "transformation",
            "orchestrator",
            "processing engine",
        }
        assert {d["stored_in"] for d in payload["datasets"]} == {"PostgreSQL"}
