"""Whether a signed record still describes what runs (#42)."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime

import pytest

from qedro import config, declared, render, ropa, signoff, staleness
from qedro import vocabulary as vocabulary_module
from qedro.__main__ import main
from qedro.sources import read


def payload(lineage: str, *, activities: bool = False) -> dict:
    events, report = read(lineage)
    vocab = vocabulary_module.load()
    record = ropa.build(
        events,
        config=config.load("demo/qedro.yaml"),
        vocabulary=vocab,
        report=report,
        declared=declared.load("demo/activities.yaml", vocabulary=vocab) if activities else (),
    )
    return json.loads(render.json(record))


@pytest.fixture(scope="module")
def evidenced() -> dict:
    return payload("demo/lineage-declared")


def states(result: staleness.RecordCheck) -> dict[str, str]:
    return {a.key: a.state for a in result.activities}


class TestTheFourStates:
    def test_the_same_run_is_up_to_date_everywhere(self, evidenced):
        result = staleness.check(evidenced, copy.deepcopy(evidenced), origin="r.json")
        assert set(states(result).values()) == {staleness.UP_TO_DATE}
        assert result.counts()[staleness.UP_TO_DATE] == len(evidenced["activities"])

    def test_a_value_unchanged_on_weaker_evidence_is_stale_and_says_so(self, evidenced):
        """The finding no single record shows: the same purpose, now from the
        mapping file instead of an emitted facet."""
        fresh = payload("demo/lineage")
        result = staleness.check(evidenced, fresh, origin="r.json")
        dunning = next(a for a in result.activities if a.key == "acme.billing/dunning-weekly")
        assert dunning.state == staleness.STALE
        purpose = next(c for c in dunning.changes if c.field == "purpose")
        assert purpose.before.value == purpose.after.value == "debt-collection"
        assert purpose.regression

    def test_a_changed_value_is_stale_and_names_the_field(self, evidenced):
        fresh = copy.deepcopy(evidenced)
        fresh["activities"][0]["purpose"]["value"] = "something-else"
        result = staleness.check(evidenced, fresh, origin="r.json")
        (stale,) = [a for a in result.activities if a.state == staleness.STALE]
        assert [c.field for c in stale.changes] == ["purpose"]

    def test_an_activity_only_the_fresh_run_has_is_new(self, evidenced):
        fresh = payload("demo/lineage-declared", activities=True)
        result = staleness.check(evidenced, fresh, origin="r.json")
        new = {a.key for a in result.activities if a.state == staleness.NEW}
        assert new == {"payroll-run", "support-reply-drafts"}

    def test_a_job_that_only_ran_again_is_not_stale(self, evidenced):
        fresh = copy.deepcopy(evidenced)
        for a in fresh["activities"]:
            a["runs"] += 5
            a["last_seen"] = "2027-01-01T00:00:00+00:00"
        result = staleness.check(evidenced, fresh, origin="r.json")
        assert set(states(result).values()) == {staleness.UP_TO_DATE}

    def test_a_record_that_cannot_be_compared_is_blocked_with_its_reason(self, evidenced):
        result = staleness.blocked("r.json", evidenced, "the source could not be read")
        assert result.blocked == "the source could not be read"
        assert result.counts()[staleness.BLOCKED] == len(evidenced["activities"])


class TestTheCommand:
    @pytest.fixture
    def records(self, tmp_path):
        path = tmp_path / "fraud.json"
        assert main(["ropa", "demo/lineage-declared", "--config", "demo/qedro.yaml", "--out",
                     str(path)]) == 0  # fmt: skip
        signoff.sign(path, by="A Person", state="for sign-off", at=datetime.now(UTC))
        signoff.sign(path, by="Another Person", state="approved", at=datetime.now(UTC))
        return tmp_path

    def test_it_counts_the_four_states(self, records, capsys):
        capsys.readouterr()
        args = ["status", str(records), "--against", "demo/lineage", "--config", "demo/qedro.yaml"]
        assert main(args) == 0
        out = capsys.readouterr().out
        assert "1 signed record: 0 up to date, 7 stale, 0 new, 0 blocked" in out
        assert "purpose: debt-collection, unchanged — evidence lost" in out

    def test_blocked_always_prints_its_reason(self, records, tmp_path, capsys):
        capsys.readouterr()
        missing = str(tmp_path / "nothing-here")
        args = ["status", str(records), "--against", missing, "--config", "demo/qedro.yaml"]
        assert main(args) == 0
        out = capsys.readouterr().out
        assert "blocked: the fresh run from" in out and "could not be built" in out
        assert "0 up to date, 0 stale, 0 new, 7 blocked" in out

    def test_a_record_nobody_signed_is_not_compared(self, tmp_path, capsys):
        path = tmp_path / "draft.json"
        assert main(["ropa", "demo/lineage", "--config", "demo/qedro.yaml", "--out",
                     str(path)]) == 0  # fmt: skip
        capsys.readouterr()
        args = ["status", str(tmp_path), "--against", "demo/lineage", "--config", "demo/qedro.yaml"]
        assert main(args) == 0
        out = capsys.readouterr().out
        assert "no signed Art. 30 records" in out
        assert "1 record not signed off, so not compared" in out
