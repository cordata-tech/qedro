"""The provenance projection.

Two things carry the weight, and both are about *not knowing*:

**A chain that ends is not a chain that is complete.** The walk stops for three
different reasons — a genuine source, a producing run outside the window, or
the depth cap — and they are indistinguishable unless the artefact says which.

**Unknown is not unsigned.** OpenLineage has no standard place for whether a
commit was signed, so the common case is silence. Reporting that as *not
signed* would be inventing a finding; reporting it as fine would be worse. It
is a third state, and it withholds the mark without ever being rendered as the
second.
"""

from __future__ import annotations

from qedro import config
from qedro.events import parse_event
from qedro.provenance import DEPTH, build, resolve
from qedro.sources import ReadReport

CONTROLLER = "controller: ACME GmbH\n"
REPO = "https://github.com/acme/platform"


def event(
    job="curate",
    namespace="acme.crm",
    reads=(),
    writes=(),
    commit="abc123def456",
    signed=None,
    when="2026-03-01T10:00:00Z",
    run="r1",
    event_type="COMPLETE",
):
    """One event, with as much or as little provenance evidence as wanted."""
    job_facets = {}
    if commit is not None:
        job_facets["sourceCodeLocation"] = {
            "_producer": "https://example.test",
            "type": "git",
            "repoUrl": REPO,
            "version": commit,
            "branch": "main",
            "path": f"models/{job}.sql",
        }
    run_facets = {}
    if signed is not None:
        run_facets["cordata_provenance"] = {
            "_producer": "https://example.test",
            "descriptor_git_commit_signed": signed,
        }

    raw = {
        "eventType": event_type,
        "eventTime": when,
        "run": {"runId": run, "facets": run_facets},
        "job": {"namespace": namespace, "name": job, "facets": job_facets},
        "inputs": [{"namespace": "wh", "name": n} for n in reads],
        "outputs": [{"namespace": "wh", "name": n} for n in writes],
    }
    parsed = parse_event(raw)
    assert parsed is not None
    return parsed


def chain(events, dataset, *, cfg="", report=None, **kw):
    if "controller" not in cfg:
        cfg = CONTROLLER + cfg
    return build(events, dataset=dataset, config=config.parse(cfg), report=report, **kw)


class TestWalkingBackwards:
    def test_one_hop(self):
        out = chain([event(writes=["scores"], reads=["raw"])], "wh/scores")
        assert [s.dataset for s in out.steps] == ["wh/scores", "wh/raw"]
        assert out.steps[0].production is not None
        assert out.steps[0].production.job == "acme.crm/curate"

    def test_several_hops_in_depth_order(self):
        events = [
            event(job="a", writes=["final"], reads=["mid"]),
            event(job="b", writes=["mid"], reads=["raw"]),
        ]
        out = chain(events, "wh/final")
        assert [(s.depth, s.dataset) for s in out.steps] == [
            (0, "wh/final"),
            (1, "wh/mid"),
            (2, "wh/raw"),
        ]

    def test_the_code_and_commit_come_from_the_standard_facet(self):
        out = chain([event(writes=["scores"], commit="0123456789abcdef")], "wh/scores")
        code = out.steps[0].production.code
        assert code.repository == REPO
        assert code.commit == "0123456789abcdef"
        assert code.short == "0123456789ab"
        assert code.branch == "main"

    def test_the_latest_run_is_followed_and_the_others_are_counted(self):
        # *The latest* must never read as *the only*.
        events = [
            event(run="r1", when="2026-03-01T10:00:00Z", writes=["scores"], commit="old"),
            event(run="r2", when="2026-03-05T10:00:00Z", writes=["scores"], commit="new"),
        ]
        out = chain(events, "wh/scores")
        assert out.steps[0].production.code.commit == "new"
        assert out.steps[0].also_produced_by == 1

    def test_a_cycle_does_not_hang(self):
        events = [
            event(job="a", writes=["x"], reads=["y"]),
            event(job="b", writes=["y"], reads=["x"]),
        ]
        out = chain(events, "wh/x")
        assert {s.dataset for s in out.steps} == {"wh/x", "wh/y"}

    def test_events_with_no_timestamp_do_not_break_the_ordering(self):
        # Two undated events would compare None against None and raise.
        events = [
            event(run="r1", when=None, writes=["scores"]),
            event(run="r2", when=None, writes=["scores"]),
        ]
        assert chain(events, "wh/scores").steps[0].production is not None


class TestAChainThatEndsIsNotAChainThatIsComplete:
    def test_a_dataset_nothing_produced_says_so(self):
        out = chain([event(writes=["scores"], reads=["raw"])], "wh/scores")
        [source] = [s for s in out.steps if s.dataset == "wh/raw"]
        assert source.production is None
        assert "nothing in the window produced it" in source.ended

    def test_and_it_is_a_reason_the_mark_is_withheld(self):
        out = chain([event(writes=["scores"], reads=["raw"], signed=True)], "wh/scores")
        assert not out.complete
        assert any("may be a source" in r for r in out.completeness.reasons)

    def test_the_depth_limit_is_stated_rather_than_silent(self):
        events = [
            event(job=f"j{n}", writes=[f"d{n}"], reads=[f"d{n + 1}"], signed=True) for n in range(6)
        ]
        out = chain(events, "wh/d0", depth=2)
        stopped = [s for s in out.steps if "depth limit" in s.ended]
        assert stopped
        assert out.scope.ends_at_depth == len(stopped)
        assert any("depth limit of 2" in r for r in out.completeness.reasons)

    def test_the_two_kinds_of_ending_are_counted_apart(self):
        events = [event(job="a", writes=["x"], reads=["y"]), event(job="b", writes=["y"])]
        out = chain(events, "wh/x", depth=1)
        assert out.scope.ends_at_depth == 1
        assert out.scope.ends_unproduced == 0

    def test_the_requested_dataset_being_unproduced_is_its_own_reason(self):
        out = chain([event(writes=["other"])], "wh/scores")
        assert not out.complete
        assert any("there is no chain to follow" in r for r in out.completeness.reasons)


class TestUnknownIsNotUnsigned:
    def test_nothing_reported_is_a_third_state(self):
        out = chain([event(writes=["scores"])], "wh/scores")
        signature = out.steps[0].production.signature
        assert signature.signed is None
        assert not signature.known
        assert "unknown" in signature.describe()

    def test_it_withholds_the_mark(self):
        out = chain([event(writes=["scores"])], "wh/scores")
        assert not out.complete
        assert any("unknown is not the same as unsigned" in r for r in out.completeness.reasons)

    def test_but_is_never_reported_as_unsigned(self):
        out = chain([event(writes=["scores"])], "wh/scores")
        assert not any("not signed" in r for r in out.completeness.reasons)

    def test_an_explicit_false_is_a_different_and_louder_reason(self):
        out = chain([event(writes=["scores"], signed=False)], "wh/scores")
        assert any("reported as not signed" in r for r in out.completeness.reasons)
        assert out.steps[0].production.signature.known

    def test_a_signature_names_what_reported_it(self):
        out = chain([event(writes=["scores"], signed=True)], "wh/scores")
        assert out.steps[0].production.signature.reported_by == "cordata_provenance"

    def test_no_code_location_at_all_is_its_own_reason(self):
        out = chain([event(writes=["scores"], commit=None, signed=True)], "wh/scores")
        assert not out.steps[0].production.code
        assert any("emitted no code location" in r for r in out.completeness.reasons)


class TestTheMark:
    def test_earned_when_every_step_shows_a_signed_commit(self):
        # The strongest claim any projection makes, so the bar is the highest.
        out = chain([event(writes=["scores"], signed=True)], "wh/scores")
        assert out.complete
        assert out.completeness.reasons == ()
        assert out.steps[0].production.authorised

    def test_withheld_when_one_step_of_several_cannot_show_one(self):
        events = [
            event(job="a", writes=["final"], reads=["mid"], signed=True),
            event(job="b", writes=["mid"], signed=None),
        ]
        out = chain(events, "wh/final")
        assert not out.complete
        assert len(out.unauthorised) == 1

    def test_withheld_when_the_read_was_degraded(self):
        report = ReadReport(origin="./x", events=1, skipped_records=3)
        out = chain([event(writes=["scores"], signed=True)], "wh/scores", report=report)
        assert not out.complete

    def test_a_signed_commit_with_no_commit_id_is_not_authorised(self):
        # A signature on nothing identifiable proves nothing.
        out = chain([event(writes=["scores"], commit=None, signed=True)], "wh/scores")
        assert not out.steps[0].production.authorised


class TestScope:
    def test_it_counts_evidence_rather_than_asserting_it(self):
        events = [
            event(job="a", writes=["final"], reads=["mid"], signed=True),
            event(job="b", writes=["mid"], commit=None),
        ]
        out = chain(events, "wh/final")
        assert out.scope.steps == 2
        assert out.scope.with_commit == 1
        assert out.scope.with_signature == 1

    def test_it_makes_no_claim_about_domains(self):
        # A chain is about one dataset. Carrying the declared domains through
        # would report every one of them as silent, which is another
        # artefact's finding and false in this one.
        out = chain([event(writes=["scores"], signed=True)], "wh/scores", cfg="domains: [a, b]\n")
        assert out.scope.domains_silent == ()

    def test_the_default_depth_is_reported_not_assumed(self):
        assert chain([event(writes=["s"])], "wh/s").scope.depth_limit == DEPTH


class TestResolvingWhatTheUserTyped:
    def test_a_bare_name_matches(self):
        events = [event(writes=["scores"])]
        assert resolve(events, "scores") == ["wh/scores"]

    def test_a_full_key_matches_exactly(self):
        events = [event(writes=["scores"])]
        assert resolve(events, "wh/scores") == ["wh/scores"]

    def test_an_ambiguous_name_returns_every_candidate(self):
        # Picking the first would produce a chain for a dataset the user did
        # not ask about, and nothing downstream would ever say so.
        events = [
            event(job="a", writes=["customers"]),
            parse_event(
                {
                    "eventType": "COMPLETE",
                    "eventTime": "2026-03-01T10:00:00Z",
                    "run": {"runId": "r2"},
                    "job": {"namespace": "acme.crm", "name": "b"},
                    "outputs": [{"namespace": "lake", "name": "customers"}],
                }
            ),
        ]
        assert resolve(events, "customers") == ["lake/customers", "wh/customers"]

    def test_an_exact_key_wins_over_a_bare_match(self):
        events = [event(writes=["customers"])]
        assert resolve(events, "wh/customers") == ["wh/customers"]

    def test_nothing_matching_is_an_empty_list_not_a_guess(self):
        assert resolve([event(writes=["scores"])], "nope") == []


class TestOtherRunsMeansOtherRuns:
    """Found against a real dbt export.

    dbt declares a model's outputs on START *and* on COMPLETE, so counting
    events rather than runs reported one run as two — and the chain printed
    "1 other run wrote this in the window" about a run that had written it
    once. A false sentence in the artefact, which is the one kind of bug this
    project cannot tolerate.
    """

    def test_a_start_and_a_complete_of_one_run_are_one_run(self):
        events = [
            event(run="same", event_type="START", writes=["scores"]),
            event(run="same", event_type="COMPLETE", writes=["scores"]),
        ]
        assert chain(events, "wh/scores").steps[0].also_produced_by == 0

    def test_two_genuinely_different_runs_are_counted(self):
        events = [
            event(run="r1", when="2026-03-01T10:00:00Z", writes=["scores"]),
            event(run="r2", when="2026-03-02T10:00:00Z", writes=["scores"]),
        ]
        assert chain(events, "wh/scores").steps[0].also_produced_by == 1

    def test_and_the_run_followed_is_the_later_one(self):
        events = [
            event(run="old", when="2026-03-01T10:00:00Z", writes=["scores"], commit="a"),
            event(run="new", when="2026-03-05T10:00:00Z", writes=["scores"], commit="b"),
            event(run="new", when="2026-03-05T10:00:01Z", writes=["scores"], commit="b"),
        ]
        step = chain(events, "wh/scores").steps[0]
        assert step.production.code.commit == "b"
        assert step.also_produced_by == 1


class TestResolvingAQualifiedName:
    """Found against a real dbt export, where a dataset is
    `duckdb://probe.duckdb/probe.main.orders_explicit` and the table anybody
    types is `orders_explicit`. The README promised a bare name would do."""

    def test_the_last_dotted_segment_matches(self):
        events = [event(writes=["probe.main.orders_explicit"])]
        assert resolve(events, "orders_explicit") == ["wh/probe.main.orders_explicit"]

    def test_the_qualified_name_still_matches(self):
        events = [event(writes=["probe.main.orders_explicit"])]
        assert resolve(events, "probe.main.orders_explicit") == ["wh/probe.main.orders_explicit"]

    def test_an_exact_name_beats_a_dotted_suffix(self):
        # `orders` as a table in its own right must not lose to
        # `warehouse.orders` just because the suffix also matches.
        events = [event(job="a", writes=["orders"]), event(job="b", writes=["mart.orders"])]
        assert resolve(events, "orders") == ["wh/orders"]

    def test_an_ambiguous_suffix_returns_both(self):
        events = [
            event(job="a", writes=["raw.customers"]),
            event(job="b", writes=["mart.customers"]),
        ]
        assert resolve(events, "customers") == ["wh/mart.customers", "wh/raw.customers"]


class TestFileDatasetsAsTheCapturesSendThem:
    """#23, against the two real captures that send `file` and absolute paths."""

    def test_neither_capture_prints_a_double_slash_in_any_format(self):
        from pathlib import Path

        from qedro import render, vocabulary
        from qedro import ropa as ropa_module
        from qedro.sources import read_dir

        for fixture in ("airflow-3.3.1", "spark-4.2.0"):
            events, _ = read_dir(Path("tests/fixtures") / fixture)
            record = ropa_module.build(
                events, config=config.parse("controller: X\n"), vocabulary=vocabulary.load()
            )
            for fmt in ("text", "markdown", "json"):
                out = render.FORMATS[fmt](record)
                assert "file//" not in out, f"{fixture}/{fmt}"
                # The markdown table counts datasets rather than naming them.
                if fmt != "markdown":
                    assert "file:///" in out, f"{fixture}/{fmt}"

    def test_the_printed_spelling_the_file_name_and_the_old_spelling_all_resolve(self):
        from pathlib import Path

        from qedro.sources import read_dir

        events, _ = read_dir(Path("tests/fixtures/airflow-3.3.1"))
        wanted = ["file:///data/curated/orders_scored.parquet"]
        assert resolve(events, "file:///data/curated/orders_scored.parquet") == wanted
        assert resolve(events, "orders_scored.parquet") == wanted
        assert resolve(events, "file//data/curated/orders_scored.parquet") == wanted


def test_no_existing_key_changed():
    # #23 changes a key only for the bare `file` namespace or an absolute name.
    # The demo and the dbt capture have neither, so every key there must be
    # exactly what it was.
    from pathlib import Path

    from qedro.sources import read_dir

    for source in ("demo/lineage", "demo/lineage-declared", "tests/fixtures/dbt-1.53"):
        events, _ = read_dir(Path(source))
        datasets = [d for e in events for d in e.datasets]
        assert datasets, source
        assert all(d.key == d.legacy_key for d in datasets), source


class TestEverySignatureSpellingIsRead:
    """`docs/compatibility.md` says three facet names report a signed commit.

    Only `cordata_provenance` had a test, and a row may only say `works` when a
    test names it.
    """

    @staticmethod
    def signed_by(facet_name):
        parsed = parse_event(
            {
                "eventType": "COMPLETE",
                "eventTime": "2026-03-01T10:00:00Z",
                "run": {
                    "runId": "r1",
                    "facets": {facet_name: {"descriptor_git_commit_signed": True}},
                },
                "job": {"namespace": "acme.fraud", "name": "scored"},
                "outputs": [{"namespace": "wh", "name": "scores"}],
            }
        )
        assert parsed is not None
        return parsed

    def test_each_spelling_reports_a_signature(self):
        from qedro.provenance import SIGNATURE_FACETS

        assert SIGNATURE_FACETS == ("cordata_provenance", "gitProvenance", "provenance")
        for name in SIGNATURE_FACETS:
            out = chain([self.signed_by(name)], "wh/scores")
            signature = out.steps[0].production.signature
            assert (signature.signed, signature.reported_by) == (True, name), name
