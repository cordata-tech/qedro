"""The assertion-history projection.

One distinction carries the whole module, and it is the one a future
simplification would remove because it looks like noise:

    **A dataset with no failures and a dataset with no checks are opposites,
    and every summary anybody writes renders them identically.**

So the tests for `unchecked` are written as carefully as the tests for the
assertions themselves, and the mark is tested in both directions — several for
each condition that withholds it, and one that it *is* earned when every
dataset in view was checked. Without the second, a change that withheld the
mark unconditionally would pass everything else.
"""

from __future__ import annotations

from datetime import UTC, datetime

from qedro import config
from qedro.events import parse_event
from qedro.quality import build
from qedro.sources import ReadReport

CONTROLLER = "controller: ACME GmbH\n"


def event(
    job="scores-validated",
    namespace="acme.fraud",
    reads="wh/scores",
    assertions=None,
    when="2026-03-01T10:00:00Z",
    run="r1",
    writes=None,
):
    """One COMPLETE event, optionally asserting things about what it read."""
    dataset_namespace, _, name = reads.partition("/")
    raw = {
        "eventType": "COMPLETE",
        "eventTime": when,
        "run": {"runId": run},
        "job": {"namespace": namespace, "name": job},
        "inputs": [{"namespace": dataset_namespace, "name": name}],
    }
    if assertions is not None:
        raw["inputs"][0]["inputFacets"] = {
            "dataQualityAssertions": {
                "_producer": "https://example.test",
                "_schemaURL": "https://example.test/s.json",
                "assertions": assertions,
            }
        }
    if writes:
        ns, _, out_name = writes.partition("/")
        raw["outputs"] = [{"namespace": ns, "name": out_name}]

    parsed = parse_event(raw)
    assert parsed is not None
    return parsed


def check(assertion="expect_column_values_to_not_be_null", column="tx_id", success=True):
    return {"assertion": assertion, "column": column, "success": success}


def record(events, *, cfg="", report=None, **kw):
    if "controller" not in cfg:
        cfg = CONTROLLER + cfg
    return build(events, config=config.parse(cfg), report=report, **kw)


class TestReadingTheFacet:
    def test_assertions_arrive_from_the_input_facet(self):
        # `dataQualityAssertions` is an *input* facet, not a dataset facet.
        # The parser dropped that side entirely until this projection needed it.
        out = record([event(assertions=[check()])])
        [dataset] = out.datasets
        assert dataset.key == "wh/scores"
        assert [e.assertion for e in dataset.expectations] == [
            "expect_column_values_to_not_be_null"
        ]

    def test_an_expectation_accumulates_across_runs(self):
        events = [
            event(run=f"r{n}", when=f"2026-03-0{n}T10:00:00Z", assertions=[check()])
            for n in range(1, 5)
        ]
        [dataset] = record(events).datasets
        [expectation] = dataset.expectations
        assert expectation.runs == 4
        assert dataset.runs == 4
        assert expectation.holds

    def test_a_failure_is_dated_not_only_counted(self):
        events = [
            event(run="r1", when="2026-03-01T10:00:00Z", assertions=[check()]),
            event(run="r2", when="2026-03-02T10:00:00Z", assertions=[check(success=False)]),
            event(run="r3", when="2026-03-03T10:00:00Z", assertions=[check()]),
        ]
        [dataset] = record(events).datasets
        [expectation] = dataset.expectations
        assert expectation.failures == 1
        assert expectation.last_failure == datetime(2026, 3, 2, 10, tzinfo=UTC)
        assert not expectation.holds
        assert not dataset.holds

    def test_an_assertion_with_no_reported_outcome_is_not_a_pass(self):
        # Silence is not success. The opposite default would turn an emitter
        # that forgot the field into a green row.
        out = record([event(assertions=[{"assertion": "expect_something", "column": "x"}])])
        [dataset] = out.datasets
        assert dataset.failures == 1

    def test_the_same_assertion_on_two_columns_is_two_expectations(self):
        out = record([event(assertions=[check(column="a"), check(column="b")])])
        [dataset] = out.datasets
        assert len(dataset.expectations) == 2

    def test_a_malformed_assertion_list_is_skipped_not_raised_on(self):
        # Evidence is skipped and counted, never fatal. Same rule as the reader.
        out = record(
            [
                event(assertions="not a list"),  # type: ignore[arg-type]
                event(reads="wh/other", assertions=[check(), "nonsense", {"no": "assertion"}]),
            ]
        )
        assert [d.key for d in out.datasets] == ["wh/other"]
        assert out.datasets[0].checks == 1


class TestNotCheckedIsNotPassed:
    """The half of the artefact that is about absence."""

    def test_a_dataset_seen_but_never_asserted_is_named(self):
        out = record([event(assertions=[check()]), event(reads="wh/untouched")])
        assert out.unchecked == ("wh/untouched",)

    def test_it_is_a_reason_the_mark_is_withheld(self):
        out = record([event(assertions=[check()]), event(reads="wh/untouched")])
        assert not out.complete
        assert any("carry no assertions at all" in r for r in out.completeness.reasons)

    def test_outputs_count_as_datasets_in_view(self):
        # A table nothing asserts anything about is unchecked whether it was
        # read or written. Writing it is if anything the stronger claim.
        out = record([event(assertions=[check()], writes="wh/derived")])
        assert "wh/derived" in out.unchecked

    def test_an_estate_with_no_assertions_anywhere_says_so_once(self):
        out = record([event(reads="wh/a"), event(reads="wh/b")])
        assert out.datasets == ()
        assert out.unchecked == ("wh/a", "wh/b")
        assert any("no history to report" in r for r in out.completeness.reasons)


class TestTheMark:
    def test_earned_when_every_dataset_in_view_was_checked(self):
        out = record([event(assertions=[check()])])
        assert out.complete
        assert out.completeness.reasons == ()

    def test_a_failing_expectation_does_not_withhold_it(self):
        # The mark says *this account of what was checked is complete*, not
        # *the data is good*. Conflating the two gives somebody a reason to
        # stop emitting the assertion that fails.
        out = record([event(assertions=[check(success=False)])])
        assert out.complete
        assert out.failing

    def test_withheld_when_a_declared_domain_produced_nothing(self):
        out = record([event(assertions=[check()])], cfg="domains: [fraud, marketing]\n")
        assert not out.complete
        assert any("marketing" in r for r in out.completeness.reasons)

    def test_withheld_when_the_read_was_degraded(self):
        report = ReadReport(origin="./x", events=1, skipped_records=2)
        out = record([event(assertions=[check()])], report=report)
        assert not out.complete

    def test_withheld_on_an_empty_window(self):
        out = record([])
        assert not out.complete
        assert any("nothing was recorded" in r for r in out.completeness.reasons)


class TestScope:
    def test_it_counts_checked_and_unchecked_apart(self):
        out = record([event(assertions=[check()]), event(reads="wh/b"), event(reads="wh/c")])
        assert out.scope.datasets == 3
        assert out.scope.checked == 1
        assert out.scope.unchecked == 2

    def test_it_counts_assertions_and_failures(self):
        out = record([event(assertions=[check(), check(column="b", success=False)])])
        assert out.scope.checks == 2
        assert out.scope.failures == 1

    def test_the_window_is_the_one_resolved_not_the_one_typed(self):
        out = record(
            [
                event(run="r1", when="2026-03-01T10:00:00Z", assertions=[check()]),
                event(run="r2", when="2026-03-05T10:00:00Z", assertions=[check()]),
            ]
        )
        assert out.scope.since == datetime(2026, 3, 1, 10, tzinfo=UTC)
        assert out.scope.until == datetime(2026, 3, 5, 10, tzinfo=UTC)

    def test_the_standing_sentence_is_about_checking_not_about_processing(self):
        # Each projection's out-of-view sentence has to be true of *that*
        # artefact. Inheriting ropa's would say the wrong thing confidently.
        assert "not checked" in record([event()]).scope.OUT_OF_VIEW


class TestDomainFiltering:
    def test_only_the_named_domain_survives(self):
        events = [
            event(namespace="acme.fraud", reads="wh/fraud_x", assertions=[check()]),
            event(namespace="acme.billing", reads="wh/bill_x", assertions=[check()]),
        ]
        out = record(events, domains=["fraud"])
        assert [d.key for d in out.datasets] == ["wh/fraud_x"]

    def test_it_narrows_the_unchecked_list_too(self):
        # A filtered history that still counted other domains' unchecked
        # datasets would be reporting on something it was told to exclude.
        events = [
            event(namespace="acme.fraud", reads="wh/fraud_x", assertions=[check()]),
            event(namespace="acme.billing", reads="wh/bill_x"),
        ]
        out = record(events, domains=["fraud"])
        assert out.unchecked == ()
        assert out.complete

    def test_a_domain_nobody_emitted_for_leaves_an_empty_history(self):
        out = record([event(assertions=[check()])], domains=["nowhere"])
        assert out.datasets == ()
        assert not out.complete


class TestWhichDomainADatasetBelongsTo:
    """The domain that writes a dataset owns it.

    The first version attributed by whichever job was read first, which made a
    shared dataset's domain depend on file order — and `--domain billing` then
    listed crm tables as unchecked. A producing domain owning its data product
    is both the mesh convention and the only answer that does not move.
    """

    def test_the_writing_domain_wins_over_a_reading_one(self):
        events = [
            event(namespace="acme.crm", job="curate", reads="wh/raw", writes="wh/customers"),
            event(namespace="acme.billing", job="invoice", reads="wh/customers"),
        ]
        out = record(events, domains=["crm"])
        assert "wh/customers" in out.unchecked

        out = record(events, domains=["billing"])
        assert "wh/customers" not in out.unchecked

    def test_and_still_wins_when_the_reader_was_seen_first(self):
        events = [
            event(namespace="acme.billing", job="invoice", reads="wh/customers"),
            event(namespace="acme.crm", job="curate", reads="wh/raw", writes="wh/customers"),
        ]
        assert "wh/customers" in record(events, domains=["crm"]).unchecked

    def test_a_source_table_belongs_to_whoever_reads_it(self):
        # Nothing in view wrote it, so the reading domain is the only domain
        # that has said anything about it at all.
        events = [event(namespace="acme.fraud", reads="wh/vendor_feed")]
        assert record(events, domains=["fraud"]).unchecked == ("wh/vendor_feed",)


class TestTheDomainGuessIsStated:
    """The same statement `ropa` makes, from the same `Config`. See #9."""

    def test_a_mapped_writer_makes_the_dataset_s_domain_mapped(self):
        events = [
            event(namespace="weird_ns", job="curate", reads="wh/raw", writes="wh/customers"),
            event(namespace="weird_ns", job="curate", reads="wh/customers", writes="wh/scores"),
        ]
        cfg = 'domains: [crm]\njobs:\n  "weird_ns/*": {domain: crm}\n'
        out = record(events, cfg=cfg)
        assert (out.scope.domains_guessed, out.scope.domains_mapped) == ((), ("crm",))

    def test_the_silent_reason_is_the_shared_one(self):
        events = [event(namespace="dbt", assertions=[check()])]
        out = record(events, cfg="domains: [orders]\n")
        assert out.scope.domains_source() == "dbt guessed from the job namespace"
        assert any(
            "the domain in view named dbt was guessed" in r for r in out.completeness.reasons
        )
