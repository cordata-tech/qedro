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


class TestDeclaredActivities:
    """cordata-tech/qedro#6: processing with no lineage, stated rather than invisible."""

    def declared(self, **overrides):
        from qedro import declared

        spec = {"purpose": "payroll", "legal_basis": "legal-obligation", "domain": "hr"}
        spec.update(overrides)
        return declared.parse({"activities": {"payroll-saas": spec}}, origin="t", vocabulary=WORDS)

    def test_they_sit_beside_the_activities_not_among_them(self):
        out = record([event(facet=EVIDENCED)], declared=self.declared())
        assert len(out.activities) == 1
        assert [d.name for d in out.declared] == ["payroll-saas"]

    def test_they_do_not_change_what_the_scope_says_was_looked_at(self):
        with_declared = record([event(facet=EVIDENCED)], declared=self.declared())
        without = record([event(facet=EVIDENCED)])
        for attr in ("jobs", "datasets", "events", "evidenced", "from_mapping", "undeclared"):
            assert getattr(with_declared.scope, attr) == getattr(without.scope, attr), attr
        assert with_declared.scope.declared == 1

    def test_the_scope_names_them_on_their_own_line(self):
        out = record([event(facet=EVIDENCED)], declared=self.declared())
        assert ("declared", "1 activity declared with no lineage") in out.scope.lines()

    def test_a_record_with_none_has_no_declared_line(self):
        out = record([event(facet=EVIDENCED)])
        assert all(label != "declared" for label, _ in out.scope.lines())

    def test_they_withhold_the_mark(self):
        assert record([event(facet=EVIDENCED)]).complete
        out = record([event(facet=EVIDENCED)], declared=self.declared())
        assert not out.complete
        assert any("declared with no lineage" in r for r in out.completeness.reasons)

    def test_a_record_of_nothing_but_declared_activities_says_both_things(self):
        out = record([], declared=self.declared())
        reasons = " ".join(out.completeness.reasons)
        assert "declared with no lineage" in reasons
        assert "no processing activities were found" in reasons

    def test_a_declared_activity_does_not_make_its_domain_stop_being_silent(self):
        out = record(
            [event(facet=EVIDENCED)],
            cfg="domains: [fraud, hr]\n",
            declared=self.declared(),
        )
        assert out.scope.domains_silent == ("hr",)

    def test_the_out_of_view_sentence_is_true_with_and_without_them(self):
        sentence = record([event(facet=EVIDENCED)]).scope.OUT_OF_VIEW
        assert "unless they are declared" in sentence
        assert "not represented here" in sentence

    def test_the_plural_follows_the_count(self):
        from qedro import declared

        two = declared.parse(
            {"activities": {"a": {"purpose": "p"}, "b": {"purpose": "q"}}},
            origin="t",
            vocabulary=WORDS,
        )
        out = record([event(facet=EVIDENCED)], declared=two)
        assert any("2 activities are declared" in r for r in out.completeness.reasons)
        assert ("declared", "2 activities declared with no lineage") in out.scope.lines()


def orchestrated(
    *,
    parent_datasets=False,
    parent_facet=None,
    child_names_run="parent-run",
    child_facet=EVIDENCED,
):
    """An invocation job and one child whose run names the invocation's run."""
    parent = {
        "eventType": "COMPLETE",
        "eventTime": "2026-03-01T09:59:00Z",
        "run": {"runId": "parent-run"},
        "job": {"namespace": "dbt", "name": "dbt-run-project", "facets": {}},
    }
    if parent_datasets:
        parent["outputs"] = [{"namespace": "wh", "name": "run_log"}]
    if parent_facet:
        parent["job"]["facets"]["processing"] = parent_facet
    child = {
        "eventType": "COMPLETE",
        "eventTime": "2026-03-01T10:00:00Z",
        "run": {
            "runId": "child-run",
            "facets": {
                "parent": {
                    "run": {"runId": child_names_run},
                    "job": {"namespace": "dbt", "name": "dbt-run-project"},
                }
            },
        },
        "job": {"namespace": "dbt", "name": "model.orders", "facets": {}},
        "inputs": [{"namespace": "wh", "name": "raw.orders"}],
        "outputs": [{"namespace": "wh", "name": "orders"}],
    }
    if child_facet:
        child["job"]["facets"]["processing"] = child_facet
    return [parse_event(parent), parse_event(child)]


class TestOrchestrationParents:
    """cordata-tech/qedro#8: dbt's invocation job is not a processing activity."""

    def test_a_parent_with_no_datasets_and_no_facet_is_not_listed(self):
        out = record(orchestrated())
        assert [a.key for a in out.activities] == ["dbt/model.orders"]
        assert out.scope.parents == ("dbt/dbt-run-project",)

    def test_it_is_still_counted_as_a_job_that_was_looked_at(self):
        out = record(orchestrated())
        assert out.scope.jobs == 2

    def test_and_named_in_the_scope_statement(self):
        out = record(orchestrated())
        [line] = [value for label, value in out.scope.lines() if label == "parents"]
        assert "dbt/dbt-run-project" in line
        assert line.startswith("1 job not listed as an activity — a parent run")

    def test_collapsing_it_does_not_withhold_the_mark(self):
        assert record(orchestrated()).complete

    def test_a_parent_with_datasets_of_its_own_stays_listed(self):
        out = record(orchestrated(parent_datasets=True))
        assert "dbt/dbt-run-project" in [a.key for a in out.activities]
        assert out.scope.parents == ()

    def test_a_parent_that_declares_purpose_and_basis_stays_listed(self):
        # A declaration made on a parent is never hidden by tidying the row away.
        out = record(orchestrated(parent_facet=EVIDENCED))
        assert "dbt/dbt-run-project" in [a.key for a in out.activities]

    def test_the_link_is_the_run_id_not_the_job_name(self):
        # The child names the parent job but a run that is not in view, so
        # nothing here states that this invocation is its parent.
        out = record(orchestrated(child_names_run="some-other-run"))
        assert "dbt/dbt-run-project" in [a.key for a in out.activities]

    def test_the_window_still_includes_the_parent_s_events(self):
        out = record(orchestrated())
        assert out.scope.since == datetime(2026, 3, 1, 9, 59, tzinfo=UTC)

    def test_against_real_dbt_lineage(self):
        from pathlib import Path

        from qedro.sources import read_dir

        events, report = read_dir(Path("tests/fixtures/dbt-1.53"))
        out = build(events, config=config.parse(CONTROLLER), vocabulary=WORDS, report=report)
        assert out.scope.parents == ("dbt/dbt-run-dbtprobe",)
        assert len(out.activities) == 4
        assert out.scope.jobs == 5
        assert all(a.inputs or a.outputs for a in out.activities)

    def test_against_real_airflow_lineage(self):
        # The DAG run is the parent. `notify` reads and writes nothing and is
        # not a parent, so it stays listed: no datasets alone is not the rule.
        out = real("airflow-3.3.1")
        assert out.scope.parents == ("default/orders_daily",)
        assert [a.key for a in out.activities] == [
            "default/orders_daily.extract_orders",
            "default/orders_daily.notify",
            "default/orders_daily.score_orders",
        ]
        assert out.scope.jobs == 4

    def test_against_real_spark_lineage(self):
        # The application run is the parent of every action. Spark's own
        # schema-reading actions are still listed; that is #22, and this test
        # asserts only what #8 decided, so #22 can change the count.
        out = real("spark-4.2.0")
        assert out.scope.parents == ("default/orders_enrichment",)
        keys = {a.key for a in out.activities}
        assert "default/orders_enrichment" not in keys
        assert {
            "default/orders_enrichment.adaptive_spark_plan.out_orders_enriched",
            "default/orders_enrichment.adaptive_spark_plan.out_revenue_by_region",
        } <= keys


def real(fixture):
    """A record from a captured fixture, which must read with nothing skipped."""
    from pathlib import Path

    from qedro.sources import read_dir

    events, report = read_dir(Path("tests/fixtures") / fixture)
    assert report.clean, f"{fixture}: {report.reasons()}"
    return build(events, config=config.parse(CONTROLLER), vocabulary=WORDS, report=report)


class TestTheDomainGuessIsStated:
    """A job guessed into the wrong domain makes a declared one look silent.

    openlineage-dbt names its namespace `dbt`, so every model lands in domain
    `dbt` and `domains: [orders]` reports orders as silent although its models
    emitted lineage. The guess is left alone; what changes is that the record
    says it guessed. See cordata-tech/qedro#9.
    """

    def test_a_namespace_domain_is_recorded_as_guessed(self):
        out = record([event(namespace="acme.fraud")], cfg="domains: [fraud]\n")
        assert out.activities[0].domain_guessed
        assert (out.scope.domains_guessed, out.scope.domains_mapped) == (("fraud",), ())

    def test_a_rule_s_domain_is_recorded_as_mapped(self):
        out = record(
            [event(namespace="weird_ns")],
            cfg='domains: [fraud]\njobs:\n  "weird_ns/*": {domain: fraud}\n',
        )
        assert not out.activities[0].domain_guessed
        assert (out.scope.domains_guessed, out.scope.domains_mapped) == ((), ("fraud",))

    def test_a_domain_can_be_both(self):
        out = record(
            [event(namespace="acme.fraud"), event(namespace="weird_ns")],
            cfg='domains: [fraud]\njobs:\n  "weird_ns/*": {domain: fraud}\n',
        )
        assert out.scope.domains_source() == (
            "fraud guessed from the job namespace; fraud from a mapping rule"
        )

    def test_the_source_is_stated_only_when_domains_are_in_scope(self):
        # Without `domains:` nothing in the verdict depends on the guess.
        assert record([event()]).scope.domains_source() == ""

    def test_a_silent_reason_names_the_guess_and_the_override(self):
        out = record([event(namespace="dbt", facet=EVIDENCED)], cfg="domains: [orders]\n")
        [reason] = out.completeness.reasons
        assert reason.startswith("declared in scope but produced no lineage in the window: orders")
        assert "the domain in view named dbt was guessed from the job namespace" in reason
        assert "`domain:` on a mapping rule" in reason

    def test_with_nothing_guessed_the_reason_stays_as_it_was(self):
        out = record(
            [event(namespace="weird_ns", facet=EVIDENCED)],
            cfg='domains: [fraud, hr]\njobs:\n  "weird_ns/*": {domain: fraud}\n',
        )
        assert out.completeness.reasons == (
            "declared in scope but produced no lineage in the window: hr",
        )

    def test_against_real_dbt_lineage(self):
        from pathlib import Path

        from qedro.sources import read_dir

        events, report = read_dir(Path("tests/fixtures/dbt-1.53"))
        cfg = config.parse(CONTROLLER + "domains: [orders]\n")
        out = build(events, config=cfg, vocabulary=WORDS, report=report)
        assert out.scope.domains_silent == ("orders",)
        assert out.scope.domains_source() == "dbt guessed from the job namespace"
        assert any("guessed from the job namespace" in r for r in out.completeness.reasons)


class TestTheArt30ItemsAreStated:
    """Which Art. 30(1) items the record has fields for. See cordata-tech/qedro#12."""

    def test_the_scope_names_covered_and_missing_items(self):
        # Since #13 the record has fields for five of the seven items; (d)
        # recipients and (g) security measures are not in any event.
        [line] = [v for k, v in record([event(facet=EVIDENCED)]).scope.lines() if k == "Art. 30(1)"]
        assert line.startswith("this record has fields for (a) the controller, (b) the purposes")
        assert "(c) categories of data subjects and of personal data" in line
        assert line.endswith("none for (d) categories of recipients and (g) security measures")

    def test_it_is_not_a_reason_to_withhold_the_mark(self):
        # It would fire on every run until v0.3, and a condition that always
        # fires makes the mark say nothing.
        out = record([event(facet=EVIDENCED)])
        assert out.complete
        assert not any("30(1)(c)" in r or "(g)" in r for r in out.completeness.reasons)

    def test_the_sentence_follows_the_data_when_an_item_is_added(self, monkeypatch):
        from qedro import ropa

        monkeypatch.setattr(ropa, "ART30_COVERED", frozenset({"a", "b", "c"}))
        line = ropa.art30_coverage()
        assert "(a) the controller, (b) the purposes and (c) categories" in line
        assert line.endswith(
            "none for (d) categories of recipients, (e) transfers to third "
            "countries, (f) time limits for erasure and (g) security measures"
        )

    def test_with_every_item_covered_there_is_no_none_for(self, monkeypatch):
        from qedro import ropa

        monkeypatch.setattr(ropa, "ART30_COVERED", frozenset("abcdefg"))
        assert "none for" not in ropa.art30_coverage()


def reading(name, reads=("wh/raw.customers",), writes=(), run="r1"):
    """A COMPLETE event for a job with explicit inputs and outputs."""
    parsed = parse_event(
        {
            "eventType": "COMPLETE",
            "eventTime": "2026-03-01T10:00:00Z",
            "run": {"runId": run},
            "job": {"namespace": "acme.fraud", "name": name, "facets": {}},
            "inputs": [{"namespace": n.split("/")[0], "name": n.split("/")[1]} for n in reads],
            "outputs": [{"namespace": n.split("/")[0], "name": n.split("/")[1]} for n in writes],
        }
    )
    assert parsed is not None
    return parsed


class TestReadOnlyActivitiesAreNamed:
    """Activities that read datasets and wrote none. See cordata-tech/qedro#22."""

    def test_a_job_that_only_reads_is_still_listed_and_named_in_the_scope(self):
        # No writing sibling and no parent: a genuine read-only job, such as an
        # export or a monitoring count. It stays an activity.
        out = record([reading("monitor")])
        assert [a.key for a in out.activities] == ["acme.fraud/monitor"]
        assert out.scope.read_only == ("acme.fraud/monitor",)
        [line] = [v for k, v in out.scope.lines() if k == "read only"]
        assert line == "1 activity read datasets and wrote none: acme.fraud/monitor"

    def test_a_job_that_writes_is_not_named(self):
        out = record([reading("score", writes=("wh/curated.scores",))])
        assert out.scope.read_only == ()
        assert not [k for k, _ in out.scope.lines() if k == "read only"]

    def test_a_job_with_no_datasets_is_not_called_read_only(self):
        assert record([reading("notify", reads=())]).scope.read_only == ()

    def test_it_is_not_a_reason_to_withhold_the_mark(self):
        out = record([reading("monitor")], cfg='jobs:\n  "*": {purpose: p, legal_basis: consent}\n')
        assert not any("read" in r and "wrote" in r for r in out.completeness.reasons)

    def test_against_real_spark_lineage(self):
        # Spark's own schema-reading actions are named; the two actions that
        # wrote are not, and nothing is dropped from the activities.
        out = real("spark-4.2.0")
        assert out.scope.read_only == (
            "default/orders_enrichment.collect_limit",
            "default/orders_enrichment.deserialize_to_object",
            "default/orders_enrichment.map_partitions_parallel_collection",
        )
        assert len(out.activities) == 5

    def test_the_other_captures_have_none(self):
        assert real("airflow-3.3.1").scope.read_only == ()
        assert real("dbt-1.53").scope.read_only == ()


def test_the_processing_facet_is_read_from_the_pipeline_runtime_capture():
    # The facet row in docs/compatibility.md; the emitter itself is the only one
    # that sends `processing`. Its `.validate` sub-jobs do not carry it, so not
    # every activity is evidenced, and this asserts only that some are.
    out = real("events")
    assert any(a.evidenced for a in out.activities)


def tagged(name="scored", reads=(), writes=(), run="r1", facet=EVIDENCED):
    """An event whose datasets carry the standard `tags` dataset facet.

    Each of *reads* and *writes* is `(dataset, {key: value})`; a dataset with an
    empty mapping carries no facet at all, which is what a table nobody
    classified looks like on the wire.
    """

    def side(entries):
        out = []
        for key, tags in entries:
            namespace, _, table = key.partition("/")
            dataset = {"namespace": namespace, "name": table}
            if tags:
                dataset["facets"] = {
                    "tags": {
                        "_producer": "https://example.test",
                        "tags": [{"key": k, "value": v, "source": "TEST"} for k, v in tags.items()],
                    }
                }
            out.append(dataset)
        return out

    parsed = parse_event(
        {
            "eventType": "COMPLETE",
            "eventTime": "2026-03-01T10:00:00Z",
            "run": {"runId": run},
            "job": {
                "namespace": "acme.fraud",
                "name": name,
                "facets": {"processing": dict(facet)} if facet else {},
            },
            "inputs": side(reads),
            "outputs": side(writes),
        }
    )
    assert parsed is not None
    return parsed


class TestClassificationFromTheTagsFacet:
    """Art. 30(1)(c), (e) and (f) from the standard `tags` dataset facet. See #13."""

    def a_record(self):
        return record(
            [
                tagged(
                    reads=[("wh/raw.transactions", {"data_category": "financial"})],
                    writes=[
                        (
                            "wh/curated.scores",
                            {
                                "data_category": "financial",
                                "subject_type": "customer",
                                "residency": "eu",
                                "retention": "7y",
                            },
                        )
                    ],
                )
            ]
        )

    def test_values_are_read_with_the_side_that_carried_them(self):
        # `reads health data` and `writes health data` are different claims.
        [activity] = self.a_record().activities
        [financial] = [c for c in activity.classification if c.key == "data_category"]
        assert financial.reads == ("wh/raw.transactions",)
        assert financial.writes == ("wh/curated.scores",)
        assert financial.provenance is Provenance.FACET

    def test_each_value_knows_which_art30_item_it_answers(self):
        [activity] = self.a_record().activities
        assert {c.value: c.item for c in activity.classification} == {
            "financial": "c",
            "customer": "c",
            "eu": "e",
            "7y": "f",
        }

    def test_a_dataset_with_no_tags_is_unclassified_not_uncategorised(self):
        # An input carrying no tags means the catalog holds none — nobody said —
        # and never that the table holds no personal data. See
        # cordata-tech/pipeline-runtime#3.
        out = record(
            [
                tagged(
                    reads=[("wh/vendor_feed", {})],
                    writes=[("wh/curated.scores", {"data_category": "financial"})],
                )
            ]
        )
        [activity] = out.activities
        assert activity.unclassified == ("wh/vendor_feed",)
        assert out.scope.unclassified == ("wh/vendor_feed",)

    def test_a_classification_is_never_carried_from_one_dataset_to_another(self):
        # What an activity wrote is the controller's declaration about its own
        # output; asserting it for the source invents evidence for somebody
        # else's table.
        out = record(
            [tagged(reads=[("wh/vendor_feed", {})], writes=[("wh/scores", {"residency": "eu"})])]
        )
        [residency] = [c for c in out.activities[0].classification if c.key == "residency"]
        assert residency.reads == ()
        assert residency.writes == ("wh/scores",)

    def test_a_tag_the_record_cannot_use_leaves_the_dataset_unclassified(self):
        # `sensitivity` is a level, not a category, and `domain` is a scoping
        # key. Counting either as an answer would turn them into one.
        out = record([tagged(writes=[("wh/scores", {"sensitivity": "high", "domain": "fraud"})])])
        assert out.activities[0].classification == ()
        assert out.activities[0].unclassified == ("wh/scores",)

    def test_a_value_outside_a_closed_term_is_reported_and_withholds_the_mark(self):
        out = record([tagged(writes=[("wh/scores", {"special_category": "shoe-size"})])])
        [value] = [c for c in out.activities[0].classification if c.key == "special_category"]
        assert value.unrecognised
        assert not out.complete
        assert any("shoe-size" in r for r in out.completeness.reasons)

    def test_an_open_term_takes_an_organisation_s_own_value(self):
        out = record([tagged(writes=[("wh/scores", {"data_category": "policyholder-claims"})])])
        assert not out.activities[0].classification[0].unrecognised
        assert out.complete

    def test_a_missing_classification_does_not_withhold_the_mark(self):
        # It would fire on nearly every run, and a mark that is always withheld
        # says nothing — the argument `quality` makes about an uneven history.
        out = record([tagged(writes=[("wh/scores", {})])])
        assert out.complete

    def test_the_scope_counts_activities_per_item_and_names_what_is_unclassified(self):
        out = record(
            [
                tagged(name="a", writes=[("wh/a", {"data_category": "financial"})]),
                tagged(name="b", writes=[("wh/b", {})]),
            ]
        )
        assert out.scope.activities == 2
        assert out.scope.reported == {"c": 1}
        lines = dict(out.scope.lines())
        assert "1 of 2 activities" in lines["classification"]
        assert lines["unclassified"].startswith("1 of 2 datasets carry no classification")
