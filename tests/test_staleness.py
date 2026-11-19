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


class TestRegenerate:
    @pytest.fixture
    def signed(self, tmp_path):
        path = tmp_path / "fraud.json"
        assert main(["ropa", "demo/lineage-declared", "--config", "demo/qedro.yaml", "--out",
                     str(path)]) == 0  # fmt: skip
        signoff.sign(path, by="A Person", state="for sign-off", at=datetime.now(UTC))
        signoff.sign(path, by="Another Person", state="approved", at=datetime.now(UTC))
        return path

    def regenerate(self, directory, *extra):
        return main(["status", str(directory), "--against", "demo/lineage", "--config",
                     "demo/qedro.yaml", "--regenerate", *extra])  # fmt: skip

    def test_a_stale_record_gets_a_next_version_sent_for_sign_off(self, signed, capsys):
        record_before = signed.read_bytes()
        entries_before = json.loads(signoff.sidecar(signed).read_text())["entries"]
        assert self.regenerate(signed.parent, "--as", "Laszlo") == 0
        target = signoff.next_version(signed)
        assert target.name == "fraud.next.json"
        # The signed version is untouched and still approved.
        assert signed.read_bytes() == record_before
        file = json.loads(signoff.sidecar(signed).read_text())
        assert file["entries"][: len(entries_before)] == entries_before
        assert file["record"] == "fraud.json"
        assert signoff.standing_of(signoff.read_record(signed), signoff.sidecar(signed)).state == (
            "approved"
        )
        # The new version waits for sign-off, naming who and what changed.
        (added,) = file["entries"][len(entries_before) :]
        assert added["state"] == "for sign-off" and added["by"] == "Laszlo"
        assert "7 stale activities (acme.billing/dunning-weekly" in added["note"]

    def test_it_shares_the_sign_off_file_so_approving_it_keeps_one_history(self, signed):
        assert self.regenerate(signed.parent, "--as", "Laszlo") == 0
        target = signoff.next_version(signed)
        path, _ = signoff.sign(target, by="Another Person", state="approved", at=datetime.now(UTC))
        assert path == signoff.sidecar(signed)
        # Replacing the record with its approved next version keeps the approval.
        signed.write_bytes(target.read_bytes())
        standing = signoff.standing_of(signoff.read_record(signed), signoff.sidecar(signed))
        assert standing.state == "approved" and standing.latest.by == "Another Person"

    def test_running_it_again_adds_no_second_entry(self, signed, capsys):
        assert self.regenerate(signed.parent, "--as", "Laszlo") == 0
        count = len(json.loads(signoff.sidecar(signed).read_text())["entries"])
        assert self.regenerate(signed.parent, "--as", "Laszlo") == 0
        assert len(json.loads(signoff.sidecar(signed).read_text())["entries"]) == count
        assert "this version is already for sign-off" in capsys.readouterr().out

    def test_an_up_to_date_record_is_left_alone(self, signed, capsys):
        args = ["status", str(signed.parent), "--against", "demo/lineage-declared", "--config",
                "demo/qedro.yaml", "--regenerate", "--as", "Laszlo"]  # fmt: skip
        assert main(args) == 0
        assert not signoff.next_version(signed).exists()
        assert "not regenerated: up to date" in capsys.readouterr().out

    def test_it_is_refused_without_a_name(self, signed, capsys):
        assert self.regenerate(signed.parent) != 0
        assert "--as" in capsys.readouterr().err
        assert not signoff.next_version(signed).exists()


class TestTheJson:
    @pytest.fixture
    def signed(self, tmp_path):
        path = tmp_path / "fraud.json"
        assert main(["ropa", "demo/lineage-declared", "--config", "demo/qedro.yaml", "--out",
                     str(path)]) == 0  # fmt: skip
        signoff.sign(path, by="A Person", state="for sign-off", at=datetime.now(UTC))
        signoff.sign(path, by="Another Person", state="approved", at=datetime.now(UTC))
        return path

    def status(self, directory, *args) -> dict:
        out = directory / "status.json"
        assert main(["status", str(directory), *args, "--format", "json", "--out", str(out)]) == 0
        return json.loads(out.read_text())

    def test_each_activity_has_its_state_and_qedros_words_for_each_change(self, signed):
        doc = self.status(signed.parent, "--against", "demo/lineage", "--config",
                          "demo/qedro.yaml")  # fmt: skip
        assert doc["qedro"]["projection"] == "status"
        assert doc["against"]["source"] == "demo/lineage" and doc["against"]["blocked"] is None
        (record,) = doc["records"]
        assert record["file"] == "fraud.json"
        assert record["signoff"]["state"] == "approved"
        dunning = next(
            a for a in record["check"]["activities"] if a["key"] == "acme.billing/dunning-weekly"
        )
        assert dunning["state"] == "stale"
        purpose = next(c for c in dunning["changes"] if c["field"] == "purpose")
        assert purpose["kind"] == "regressed"
        assert purpose["before"] == {"value": "debt-collection", "provenance": "facet"}
        assert purpose["says"] == "debt-collection, unchanged"
        assert purpose["costs"].startswith("evidence lost")
        assert doc["counts"] == {"up to date": 0, "stale": 7, "new": 0, "blocked": 0}

    def test_without_against_it_lists_sign_offs_and_compares_nothing(self, signed):
        doc = self.status(signed.parent)
        assert doc["against"] is None and doc["counts"] is None
        assert [r["check"] for r in doc["records"]] == [None]

    def test_a_blocked_run_says_why_in_the_json_too(self, signed, tmp_path):
        doc = self.status(signed.parent, "--against", str(tmp_path / "nothing"), "--config",
                          "demo/qedro.yaml")  # fmt: skip
        assert "could not be built" in doc["against"]["blocked"]
        assert "could not be built" in doc["records"][0]["check"]["blocked"]

    def test_the_status_file_is_never_read_back_as_a_record(self, signed, capsys):
        self.status(signed.parent)
        capsys.readouterr()
        assert main(["status", str(signed.parent)]) == 0
        out = capsys.readouterr().out
        assert "status.json" not in out and "passed over" not in out
        doc = self.status(signed.parent)
        assert [r["file"] for r in doc["records"]] == ["fraud.json"]
