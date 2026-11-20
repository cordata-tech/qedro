"""A person's sign-off beside a record (#40).

The rule under test above all others: a sign-off is printed beside the verdict
and never changes it. A signature is a person's acceptance, not evidence.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime

import pytest

from qedro import render, signoff
from qedro.__main__ import main
from qedro.errors import UsageError

from .as_text import as_text
from .test_render import PROJECTIONS, formats_for

AT = datetime(2026, 11, 17, 9, 30, tzinfo=UTC)


def written(tmp_path, projection="ropa", name="record.json"):
    """A projection's record, as `--out record.json` writes it."""
    path = tmp_path / name
    path.write_text(render.json(PROJECTIONS[projection]()), encoding="utf-8")
    return path


def approved(path, by="Erika Mustermann", prepared_by="Max Mustermann"):
    signoff.sign(path, state="for sign-off", by=prepared_by, at=AT)
    signoff.sign(path, state="approved", by=by, at=AT)
    return signoff.sidecar(path)


def ropa_payload():
    return json.loads(render.json(PROJECTIONS["ropa"]()))


class TestWhatASignOffCovers:
    """A sign-off covers what the record states, and nothing that changes merely
    because the record was built again, or by a newer qedro."""

    def test_not_the_tool_version_nor_the_signoff(self):
        payload = ropa_payload()
        changed = {**payload, "qedro": {**payload["qedro"], "version": "9.9.9"}, "signoff": {}}
        assert signoff.digest(changed) == signoff.digest(payload)

    def test_not_run_counts_timestamps_or_the_window(self):
        payload = ropa_payload()
        rebuilt = json.loads(json.dumps(payload))
        for activity in rebuilt["activities"]:
            activity["runs"] += 5
            activity["last_seen"] = "2027-01-01T00:00:00+00:00"
        rebuilt["scope"]["window"]["until"] = "2027-01-01T00:00:00+00:00"
        assert signoff.digest(rebuilt) == signoff.digest(payload)

    def test_not_a_field_a_newer_qedro_adds(self):
        payload = ropa_payload()
        upgraded = json.loads(json.dumps(payload))
        for activity in upgraded["activities"]:
            activity["ran_on"] = "dbt"
        upgraded["something_new"] = [1, 2, 3]
        assert signoff.digest(upgraded) == signoff.digest(payload)

    @pytest.mark.parametrize(
        ("where", "change"),
        [
            ("purpose", lambda a: a["purpose"].update(value="marketing")),
            ("legal basis", lambda a: a["legal_basis"].update(provenance="mapping")),
            ("writes", lambda a: a["writes"].append("wh/new_table")),
            ("recipients", lambda a: a["recipients"]["values"].append("a bureau")),
        ],
    )
    def test_any_statement_about_the_processing(self, where, change):
        payload = ropa_payload()
        changed = json.loads(json.dumps(payload))
        change(changed["activities"][0])
        assert signoff.digest(changed) != signoff.digest(payload), where

    def test_the_verdict(self):
        payload = ropa_payload()
        assert signoff.digest({**payload, "complete": not payload["complete"]}) != (
            signoff.digest(payload)
        )

    @pytest.mark.parametrize("projection", sorted(PROJECTIONS))
    def test_every_covered_field_exists_in_what_qedro_writes(self, projection):
        # A renamed field would otherwise drop out of the hash unnoticed.
        payload = json.loads(render.json(PROJECTIONS[projection]()))
        paths = signoff.COVERED[signoff.kind(payload)]
        for path in paths:
            assert _reachable(payload, path), f"{signoff.kind(payload)}: {'.'.join(path)}"

    def test_a_comparison_cannot_be_signed(self):
        with pytest.raises(UsageError, match="cannot sign"):
            signoff.digest({"qedro": {"projection": "compare"}})


def _reachable(value, path):
    """Whether *path* leads somewhere in *value*. An empty list counts, as there is
    nothing in it to miss, and so does `null` — a provenance step that ends at a
    source has no production — but a missing key does not."""
    if not path or value is None:
        return True
    head, rest = path[0], path[1:]
    if head == "*":
        return isinstance(value, list) and all(_reachable(item, rest) for item in value)
    return isinstance(value, dict) and head in value and _reachable(value[head], rest)


class TestAnOlderSignOff:
    """An entry is checked against the coverage it was made under."""

    def test_one_made_by_0_16_still_covers_the_record_it_signed(self, tmp_path):
        path = written(tmp_path)
        payload = signoff.read_record(path)
        signoff.sidecar(path).write_text(
            json.dumps(
                {
                    "qedro_signoff": 1,
                    "record": path.name,
                    "entries": [
                        {
                            "record_sha256": signoff.digest(payload, coverage=1),
                            "state": "for sign-off",
                            "by": "Erika Mustermann",
                            "at": AT.isoformat(),
                        },
                        {
                            "record_sha256": signoff.digest(payload, coverage=1),
                            "state": "approved",
                            "by": "Erika Mustermann",
                            "at": AT.isoformat(),
                        },
                    ],
                }
            )
        )
        standing = signoff.standing_of(payload, signoff.sidecar(path))
        assert standing.state == "approved"
        # It covered less than a sign-off made now would, and says so.
        assert standing.narrower
        assert "sign again to cover the rest" in standing.describe()

    def test_a_new_one_is_made_under_the_current_coverage(self, tmp_path):
        path = written(tmp_path)
        _, entry = signoff.sign(path, state="for sign-off", by="Erika Mustermann", at=AT)
        assert entry.coverage == signoff.COVERAGE
        assert json.loads(signoff.sidecar(path).read_text())["entries"][0]["coverage"] == (
            signoff.COVERAGE
        )


class TestTheStates:
    def test_a_record_starts_as_draft(self, tmp_path):
        path = written(tmp_path)
        assert signoff.load(signoff.sidecar(path)).state(signoff.read_record(path)) == "draft"

    def test_one_step_forward_at_a_time(self, tmp_path):
        path = written(tmp_path)
        with pytest.raises(UsageError, match="can go to for sign-off, not approved"):
            signoff.sign(path, state="approved", by="Erika Mustermann", at=AT)

    def test_the_whole_way_and_back_to_draft(self, tmp_path):
        path = written(tmp_path)
        steps = [("for sign-off", "Max Mustermann"), ("approved", "Erika Mustermann"),
                 ("published", "Erika Mustermann"), ("draft", "Erika Mustermann"),
                 ("for sign-off", "Max Mustermann")]  # fmt: skip
        for state, by in steps:
            signoff.sign(path, state=state, by=by, at=AT)
        payload = signoff.read_record(path)
        assert signoff.load(signoff.sidecar(path)).state(payload) == "for sign-off"

    def test_an_entry_is_only_ever_added(self, tmp_path):
        path = written(tmp_path)
        signoff.sign(path, state="for sign-off", by="Erika Mustermann", at=AT)
        before = json.loads(signoff.sidecar(path).read_text())["entries"]
        signoff.sign(path, state="approved", by="Max Mustermann", at=AT, note="checked")
        after = json.loads(signoff.sidecar(path).read_text())["entries"]
        assert after[: len(before)] == before and len(after) == len(before) + 1

    def test_a_signoff_needs_a_name(self, tmp_path):
        with pytest.raises(UsageError, match="needs a name"):
            signoff.sign(written(tmp_path), state="for sign-off", by=" ", at=AT)

    def test_only_a_record_qedro_wrote_can_be_signed(self, tmp_path):
        other = tmp_path / "other.json"
        other.write_text('{"name": "a register"}', encoding="utf-8")
        with pytest.raises(UsageError, match="no `qedro` block"):
            signoff.sign(other, state="for sign-off", by="Erika Mustermann", at=AT)


class TestAChangedRecord:
    def test_is_not_signed_off_and_names_the_earlier_signoff(self, tmp_path):
        path = written(tmp_path)
        sidecar = approved(path)
        payload = json.loads(path.read_text())
        payload["complete"] = not payload["complete"]
        standing = signoff.standing_of(payload, sidecar)
        assert standing.state == "draft"
        assert "covers an earlier version" in standing.describe()
        assert "approved by Erika Mustermann" in standing.describe()


SIGNED = [(p, f) for p in sorted(PROJECTIONS) for f in formats_for(type(PROJECTIONS[p]()))]


class TestEveryFormat:
    """The sign-off is printed beside the verdict, in every format, and nothing
    is printed when no sign-off was attached."""

    def signed(self, projection, tmp_path):
        record = PROJECTIONS[projection]()
        path = written(tmp_path, projection)
        record.signoff = signoff.standing_of(json.loads(path.read_text()), approved(path))
        return record

    @pytest.mark.parametrize(("projection", "fmt"), SIGNED)
    def test_it_is_printed_with_its_caveat(self, projection, fmt, tmp_path):
        out = as_text(render.FORMATS[fmt](self.signed(projection, tmp_path)))
        assert "approved by Erika Mustermann" in out
        assert "not evidence" in out

    @pytest.mark.parametrize(("projection", "fmt"), SIGNED)
    def test_it_never_changes_the_verdict(self, projection, fmt, tmp_path):
        plain = PROJECTIONS[projection]()
        signed = self.signed(projection, tmp_path)
        assert signed.complete == plain.complete
        assert signed.completeness.reasons == plain.completeness.reasons

    @pytest.mark.parametrize("projection", sorted(PROJECTIONS))
    def test_an_unsigned_record_is_byte_identical_to_before(self, projection):
        record = PROJECTIONS[projection]()
        assert "signoff" not in json.loads(render.json(record))
        assert "sign-off" not in render.text(record)

    def test_the_json_carries_the_state_by_name(self, tmp_path):
        record = self.signed("ropa", tmp_path)
        payload = json.loads(render.json(record))
        assert payload["signoff"]["state"] == "approved"
        assert payload["signoff"]["by"] == "Erika Mustermann"
        # Signing does not change what the signature covers.
        unsigned = json.loads(render.json(dataclasses.replace(record, signoff=None)))
        assert signoff.digest(payload) == signoff.digest(unsigned)


class TestTheCommands:
    def test_sign_then_status(self, tmp_path, capsys):
        path = written(tmp_path)
        assert main(["sign", str(path), "--as", "Max Mustermann", "--state", "for sign-off"]) == 0
        assert main(["sign", str(path), "--as", "Erika Mustermann", "--state", "approved"]) == 0
        capsys.readouterr()
        assert main(["status", str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert "approved by Erika Mustermann" in out
        assert "1 record: 0 draft, 0 for sign-off, 1 approved, 0 published" in out

    def test_a_step_that_is_not_allowed_is_a_sentence(self, tmp_path, capsys):
        path = written(tmp_path)
        assert main(["sign", str(path), "--as", "Erika Mustermann", "--state", "published"]) == 2
        assert "can go to for sign-off, not published" in capsys.readouterr().err

    def test_status_counts_json_that_is_not_a_record(self, tmp_path, capsys):
        written(tmp_path)
        (tmp_path / "register.json").write_text("{}", encoding="utf-8")
        assert main(["status", str(tmp_path)]) == 0
        assert "1 JSON file passed over" in capsys.readouterr().out

    def test_a_signoff_file_that_does_not_exist_is_refused(self, tmp_path, capsys):
        from .test_cli import _estate

        events, config = _estate(tmp_path, facet=True)
        argv = ["ropa", str(events), "--config", str(config), "--signoff", str(tmp_path / "x")]
        assert main(argv) == 2
        assert "no sign-off file" in capsys.readouterr().err

    def test_a_projection_prints_the_signoff_it_was_given(self, tmp_path, capsys):
        from .test_cli import _estate

        events, config = _estate(tmp_path, facet=True)
        base = ["ropa", str(events), "--config", str(config)]
        record = tmp_path / "record.json"
        assert main([*base, "--out", str(record)]) == 0
        sidecar = approved(record)
        capsys.readouterr()
        assert main([*base, "--signoff", str(sidecar)]) == 0
        assert "sign-off: approved by Erika Mustermann" in capsys.readouterr().out


class TestFourEyes:
    """The person who sent a version for sign-off cannot approve it (#47)."""

    def test_an_approval_by_the_preparer_is_refused_naming_both(self, tmp_path):
        path = written(tmp_path)
        signoff.sign(path, state="for sign-off", by="Erika Mustermann", at=AT)
        with pytest.raises(UsageError, match="Erika Mustermann sent this version .* for sign-off"):
            signoff.sign(path, state="approved", by="Erika Mustermann", at=AT)
        assert signoff.load(signoff.sidecar(path)).state(signoff.read_record(path)) == (
            "for sign-off"
        )

    def test_the_same_name_typed_differently_is_the_same_person(self, tmp_path):
        path = written(tmp_path)
        signoff.sign(path, state="for sign-off", by="Erika Mustermann", at=AT)
        with pytest.raises(UsageError, match="four eyes"):
            signoff.sign(path, state="approved", by="  erika   MUSTERMANN ", at=AT)

    def test_both_names_are_printed_in_every_format(self, tmp_path):
        path = written(tmp_path)
        approved(path, by="Erika Mustermann", prepared_by="Max Mustermann")
        standing = signoff.standing_of(signoff.read_record(path), signoff.sidecar(path))
        line = standing.describe()
        assert "approved by Erika Mustermann" in line
        assert "prepared by Max Mustermann" in line
        assert standing.second_person is True
        record = PROJECTIONS["ropa"]()
        record.signoff = standing
        for fmt in formats_for(type(record)):
            assert "prepared by Max Mustermann" in as_text(render.FORMATS[fmt](record))
        payload = json.loads(render.json(record))["signoff"]
        assert payload["prepared_by"] == "Max Mustermann" and payload["second_person"] is True

    def test_qedro_yaml_can_let_one_person_do_both_and_the_record_says_so(
        self, tmp_path, monkeypatch, capsys
    ):
        path = written(tmp_path)
        (tmp_path / "qedro.yaml").write_text("signoff:\n  four_eyes: false\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert main(["sign", str(path), "--as", "Erika Mustermann", "--state", "for sign-off"]) == 0
        assert main(["sign", str(path), "--as", "Erika Mustermann", "--state", "approved"]) == 0
        out = capsys.readouterr().out
        assert "with no second person: Erika Mustermann also prepared it" in out
        standing = signoff.standing_of(signoff.read_record(path), signoff.sidecar(path))
        assert standing.second_person is False

    def test_status_counts_approvals_without_a_second_person(self, tmp_path, monkeypatch, capsys):
        alone, checked = written(tmp_path, name="alone.json"), written(tmp_path, name="two.json")
        (tmp_path / "qedro.yaml").write_text("signoff:\n  four_eyes: false\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        signoff.sign(alone, state="for sign-off", by="Erika", at=AT)
        signoff.sign(alone, state="approved", by="Erika", at=AT, four_eyes=False)
        approved(checked)
        capsys.readouterr()
        assert main(["status", str(tmp_path)]) == 0
        assert "1 approval with no second person" in capsys.readouterr().out
        out = tmp_path / "status-out" / "status.json"
        out.parent.mkdir()
        assert main(["status", str(tmp_path), "--format", "json", "--out", str(out)]) == 0
        doc = json.loads(out.read_text())
        assert doc["approved_without_second_person"] == 1
        by_file = {r["file"]: r["signoff"] for r in doc["records"]}
        assert by_file["alone.json"]["second_person"] is False
        assert by_file["two.json"]["second_person"] is True

    @pytest.mark.parametrize(
        ("yaml", "message"),
        [
            ("signoff: yes\n", "should be a mapping"),
            ("signoff:\n  four_eyes: 'no'\n", "should be true or false"),
            ("signoff:\n  four_eye: false\n", "unknown keys: four_eye"),
        ],
    )
    def test_a_mistyped_setting_is_refused_rather_than_read_as_off(self, yaml, message):
        from qedro import config
        from qedro.errors import ConfigError

        with pytest.raises(ConfigError, match=message):
            config.parse(yaml)
