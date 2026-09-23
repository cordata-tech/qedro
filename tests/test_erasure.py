"""Proving an erasure reached what was derived from it — cordata-tech/qedro#4.

Two things carry the weight. **The tombstone is evidence or an assertion, never
just a date**: an emitted `lifecycleStateChange` is the instant somebody proved,
`--since` is the instant somebody typed, and a record built on the second does not
claim to be a proof. And **the list of places the proof does not reach is the
output**, so it is never quietly empty — a descendant nothing rewrote since the
erasure is named, and withholds the mark.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from qedro import config, erasure
from qedro.events import parse_event
from qedro.ropa import Provenance

CONTROLLER = "controller: ACME GmbH\n"
ERASED = "wh/crm_raw.contacts"


def at(day: int, hour: int = 10) -> datetime:
    return datetime(2026, 3, day, hour, tzinfo=UTC)


def event(
    name="job",
    *,
    reads=(),
    writes=(),
    day=1,
    hour=10,
    state="COMPLETE",
    run="",
    lifecycle="",
):
    """One event. `lifecycle` puts the standard facet on every output."""

    def side(keys):
        out = []
        for key in keys:
            namespace, _, table = key.partition("/")
            dataset = {"namespace": namespace, "name": table}
            if lifecycle:
                dataset["facets"] = {
                    "lifecycleStateChange": {
                        "_producer": "https://example.test",
                        "lifecycleStateChange": lifecycle,
                    }
                }
            out.append(dataset)
        return out

    parsed = parse_event(
        {
            "eventType": state,
            "eventTime": at(day, hour).isoformat(),
            "run": {"runId": run or f"{name}-{day}-{hour}"},
            "job": {"namespace": "acme", "name": name, "facets": {}},
            "inputs": side(reads),
            "outputs": side(writes),
        }
    )
    assert parsed is not None
    return parsed


def record(events, *, since=None, depth=erasure.DEPTH, dataset=ERASED):
    return erasure.build(
        events,
        dataset=dataset,
        config=config.parse(CONTROLLER),
        since=since,
        depth=depth,
    )


#: One hop down from the erased dataset, rewritten on the 10th.
def chain(day=10):
    return [
        event("curate", reads=[ERASED], writes=["wh/crm_curated.contacts"], day=day),
    ]


class TestTheTombstone:
    def test_an_emitted_lifecycle_event_is_evidence(self):
        events = [event("drop", writes=[ERASED], day=5, lifecycle="DROP"), *chain()]
        out = record(events)
        assert out.tombstone.provenance is Provenance.FACET
        assert out.tombstone.at == at(5)
        assert out.tombstone.state == "DROP"
        assert out.tombstone.evidenced

    @pytest.mark.parametrize("state", ["DROP", "TRUNCATE", "OVERWRITE"])
    def test_three_of_the_six_lifecycle_states_are_erasures(self, state):
        events = [event("erase", writes=[ERASED], day=5, lifecycle=state), *chain()]
        assert record(events).tombstone.evidenced

    @pytest.mark.parametrize("state", ["ALTER", "CREATE", "RENAME"])
    def test_and_the_other_three_are_not(self, state):
        # A rename is not a deletion, and reporting one as the other would claim
        # a proof that never happened.
        events = [event("touch", writes=[ERASED], day=5, lifecycle=state), *chain()]
        assert record(events, since=at(1)).tombstone.provenance is Provenance.DECLARED

    def test_since_is_an_assertion(self):
        out = record(chain(), since=at(5))
        assert out.tombstone.provenance is Provenance.DECLARED
        assert out.tombstone.at == at(5)
        assert not out.tombstone.evidenced

    def test_the_latest_erasure_wins(self):
        # An estate that truncates nightly has many; the one being proved is the
        # most recent.
        events = [
            event("drop", writes=[ERASED], day=3, lifecycle="TRUNCATE"),
            event("drop", writes=[ERASED], day=7, lifecycle="TRUNCATE"),
            *chain(),
        ]
        assert record(events).tombstone.at == at(7)

    def test_an_emitted_event_supersedes_since_and_both_are_printed(self):
        events = [event("drop", writes=[ERASED], day=5, lifecycle="DROP"), *chain()]
        out = record(events, since=at(1))
        assert out.tombstone.at == at(5)
        assert out.tombstone.asserted_at == at(1)
        # Saying the two disagree beats either silently winning.
        assert any("superseded" == label for label, _ in out.scope.lines())

    def test_a_facet_that_is_not_a_mapping_is_absent_rather_than_a_crash(self):
        raw = {
            "eventType": "COMPLETE",
            "eventTime": at(5).isoformat(),
            "run": {"runId": "r"},
            "job": {"namespace": "acme", "name": "drop", "facets": {}},
            "inputs": [],
            "outputs": [
                {
                    "namespace": "wh",
                    "name": "crm_raw.contacts",
                    "facets": {"lifecycleStateChange": []},
                }
            ],
        }
        parsed = parse_event(raw)
        assert parsed is not None
        assert record([parsed, *chain()], since=at(1)).tombstone.provenance is Provenance.DECLARED

    def test_with_neither_there_is_nothing_to_measure_against(self):
        out = record(chain())
        assert out.tombstone.at is None
        assert not out.complete
        assert any("nothing to measure" in r for r in out.completeness.reasons)


class TestTheWalk:
    def test_a_direct_consumer_is_a_descendant(self):
        out = record(chain(), since=at(5))
        [descendant] = out.descendants
        assert descendant.dataset == "wh/crm_curated.contacts"
        assert descendant.depth == 1
        assert descendant.through == "acme/curate"

    def test_it_is_transitive(self):
        events = [
            *chain(),
            event("rollup", reads=["wh/crm_curated.contacts"], writes=["wh/marts.monthly"], day=11),
        ]
        out = record(events, since=at(5))
        assert [d.dataset for d in out.descendants] == [
            "wh/crm_curated.contacts",
            "wh/marts.monthly",
        ]
        assert [d.depth for d in out.descendants] == [1, 2]

    def test_a_cycle_does_not_walk_for_ever(self):
        events = [
            *chain(),
            event("back", reads=["wh/crm_curated.contacts"], writes=[ERASED], day=11),
        ]
        assert [d.dataset for d in record(events, since=at(5)).descendants] == [
            "wh/crm_curated.contacts"
        ]

    def test_a_dataset_nothing_reads_has_no_descendants(self):
        out = record([event("other", reads=["wh/unrelated"], writes=["wh/x"])], since=at(5))
        assert out.descendants == ()
        assert any("no descendants were found" in r for r in out.completeness.reasons)
        # *Not the same as the erased data having none* — the reason says so.
        assert any("not the same as" in r for r in out.completeness.reasons)

    def test_the_walk_stops_at_the_depth_limit_and_says_so(self):
        events = list(chain())
        previous = "wh/crm_curated.contacts"
        for step in range(2, 8):
            nxt = f"wh/level_{step}"
            events.append(event(f"j{step}", reads=[previous], writes=[nxt], day=10 + step))
            previous = nxt
        out = record(events, since=at(5), depth=3)
        assert max(d.depth for d in out.descendants) == 3
        assert any(d.truncated for d in out.descendants)
        assert any("depth limit of 3" in r for r in out.completeness.reasons)


class TestWhetherTheErasureReached:
    def test_a_completed_run_after_the_tombstone_is_a_rewrite(self):
        out = record(chain(day=10), since=at(5))
        [descendant] = out.descendants
        assert descendant.reached
        assert descendant.rewritten == at(10)
        assert descendant.runs_since == 1

    def test_a_run_before_the_tombstone_is_not(self):
        out = record(chain(day=3), since=at(5))
        [descendant] = out.descendants
        assert not descendant.reached
        assert descendant.rewritten is None

    def test_a_descendant_nothing_rewrote_is_named_and_withholds_the_mark(self):
        out = record(chain(day=3), since=at(5))
        assert not out.complete
        assert [d.dataset for d in out.unreached] == ["wh/crm_curated.contacts"]
        [reason] = [r for r in out.completeness.reasons if "not been rewritten" in r]
        # Named, not counted: this list is the output, not a statistic.
        assert "wh/crm_curated.contacts" in reason

    def test_a_run_that_started_and_never_finished_is_neither(self):
        events = [
            *chain(day=3),
            event(
                "curate",
                reads=[ERASED],
                writes=["wh/crm_curated.contacts"],
                day=10,
                state="START",
                run="r-open",
            ),
        ]
        out = record(events, since=at(5))
        [descendant] = out.descendants
        assert not descendant.reached
        assert descendant.incomplete == 1
        assert any("never reported completion" in r for r in out.completeness.reasons)

    def test_a_run_that_started_and_finished_counts_once(self):
        events = [
            event("curate", reads=[ERASED], writes=["wh/c"], day=10, state="START", run="r1"),
            event(
                "curate",
                reads=[ERASED],
                writes=["wh/c"],
                day=10,
                hour=11,
                state="COMPLETE",
                run="r1",
            ),
        ]
        [descendant] = record(events, since=at(5)).descendants
        assert descendant.runs_since == 1
        assert descendant.incomplete == 0

    def test_the_latest_rewrite_is_the_one_reported(self):
        events = [
            *chain(day=10),
            event("curate", reads=[ERASED], writes=["wh/crm_curated.contacts"], day=14, run="r2"),
        ]
        [descendant] = record(events, since=at(5)).descendants
        assert descendant.rewritten == at(14)
        assert descendant.runs_since == 2


class TestTheMark:
    def test_everything_rewritten_after_an_emitted_tombstone_earns_it(self):
        events = [event("drop", writes=[ERASED], day=5, lifecycle="DROP"), *chain(day=10)]
        out = record(events)
        assert out.complete, out.completeness.reasons

    def test_an_asserted_tombstone_withholds_it_even_when_everything_was_rewritten(self):
        out = record(chain(day=10), since=at(5))
        assert not out.complete
        assert any("--since rather than from an emitted" in r for r in out.completeness.reasons)

    def test_all_four_reasons_can_appear_at_once(self):
        events = list(chain(day=3))
        previous = "wh/crm_curated.contacts"
        for step in range(2, 6):
            nxt = f"wh/level_{step}"
            events.append(event(f"j{step}", reads=[previous], writes=[nxt], day=3))
            previous = nxt
        events.append(
            event("late", reads=[ERASED], writes=["wh/open"], day=10, state="START", run="open")
        )
        out = record(events, since=at(5), depth=3)
        assert not out.complete
        assert len(out.completeness.reasons) >= 4


class TestTheScopeStatement:
    """#3: unconditional, and this one carries the limit the whole feature has."""

    def test_the_dataset_not_rows_limit_is_the_standing_sentence(self):
        out = record(chain(day=10), since=at(5))
        assert "covers datasets, not rows" in out.scope.OUT_OF_VIEW
        assert "no lineage event carries that" in out.scope.OUT_OF_VIEW
        # Propagated is not complete, and the sentence says which one this is.
        assert "not proof that it was complete" in out.scope.OUT_OF_VIEW

    def test_it_is_the_same_sentence_on_a_run_that_earns_the_mark(self):
        events = [event("drop", writes=[ERASED], day=5, lifecycle="DROP"), *chain(day=10)]
        out = record(events)
        assert out.complete
        assert "covers datasets, not rows" in out.scope.OUT_OF_VIEW

    def test_the_lines_name_the_tombstone_and_its_provenance(self):
        rows = dict(record(chain(day=10), since=at(5)).scope.lines())
        assert rows["erased"] == ERASED
        assert "not emitted" in rows["tombstone"]

    def test_and_say_so_when_it_was_emitted(self):
        events = [event("drop", writes=[ERASED], day=5, lifecycle="DROP"), *chain(day=10)]
        rows = dict(record(events).scope.lines())
        assert "emitted drop" in rows["tombstone"]

    def test_propagation_is_counted_both_ways(self):
        events = [*chain(day=10), event("stale", reads=[ERASED], writes=["wh/old"], day=3)]
        rows = dict(record(events, since=at(5)).scope.lines())
        assert rows["propagation"] == "1 of 2 rewritten since the tombstone, 1 not"


class TestTheDemoEstate:
    """The whole thing against committed events, and the only evidenced tier.

    Every other test here builds its events in memory. This one runs against
    `demo/lineage-declared`, where the erasure job emits the standard lifecycle
    facet — so the evidenced path is exercised by something a reader can open
    rather than only by a fixture written beside the assertion.
    """

    @staticmethod
    def built(**kw):
        from pathlib import Path

        from qedro.sources import read_dir

        events, report = read_dir(Path("demo/lineage-declared"))
        return erasure.build(
            events,
            dataset="warehouse/crm_raw.contacts",
            config=config.parse(CONTROLLER),
            report=report,
            **kw,
        )

    def test_the_tombstone_is_evidence_rather_than_a_typed_date(self):
        out = self.built()
        assert out.tombstone.evidenced
        assert out.tombstone.state == "OVERWRITE"
        assert out.tombstone.at == datetime(2026, 7, 22, 9, 18, tzinfo=UTC)

    def test_the_closure_is_transitive_through_three_levels(self):
        out = self.built()
        assert [(d.depth, d.dataset) for d in out.descendants] == [
            (1, "warehouse/crm_curated.customers"),
            (2, "warehouse/billing_curated.invoices"),
            (3, "warehouse/billing_curated.dunning_cases"),
        ]

    def test_the_weekly_job_is_the_hole_the_erasure_did_not_reach(self):
        # Dunning runs on Mondays and the erasure landed on a Wednesday, so the
        # window ends before it runs again. An estate where everything was
        # rewritten in time is not one anybody has.
        out = self.built()
        assert [d.dataset for d in out.unreached] == ["warehouse/billing_curated.dunning_cases"]
        assert out.scope.rewritten == 2
        assert out.scope.not_rewritten == 1

    def test_so_the_record_does_not_claim_to_be_a_proof(self):
        out = self.built()
        assert not out.complete
        # Named, and the tombstone is *not* among the reasons: it was emitted.
        [reason] = out.completeness.reasons
        assert "warehouse/billing_curated.dunning_cases" in reason
        assert "--since" not in reason

    def test_the_erasure_job_is_itself_in_the_art30_record(self):
        # It processes personal data to honour a right, which is processing. A
        # demo where the erasure job was invisible to `ropa` would be arguing
        # that erasure is somehow outside the record.
        from pathlib import Path

        from qedro import ropa, vocabulary
        from qedro.sources import read_dir

        events, report = read_dir(Path("demo/lineage-declared"))
        record = ropa.build(
            events,
            config=config.parse(CONTROLLER),
            vocabulary=vocabulary.load(),
            report=report,
        )
        [job] = [a for a in record.activities if a.key == "acme.crm/subject-erasure"]
        assert job.purpose.value == "subject-rights-handling"
        assert job.legal_basis.value == "legal-obligation"
