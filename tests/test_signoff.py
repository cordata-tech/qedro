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


def approved(path, by="Erika Mustermann"):
    signoff.sign(path, state="for sign-off", by=by, at=AT)
    signoff.sign(path, state="approved", by=by, at=AT)
    return signoff.sidecar(path)


class TestTheHash:
    def test_it_leaves_out_the_tool_version_and_the_signoff(self):
        payload = json.loads(render.json(PROJECTIONS["ropa"]()))
        changed = {**payload, "qedro": {**payload["qedro"], "version": "9.9.9"}, "signoff": {}}
        assert signoff.digest(changed) == signoff.digest(payload)

    def test_it_changes_with_anything_the_record_states(self):
        payload = json.loads(render.json(PROJECTIONS["ropa"]()))
        assert signoff.digest({**payload, "complete": not payload["complete"]}) != (
            signoff.digest(payload)
        )


class TestTheStates:
    def test_a_record_starts_as_draft(self, tmp_path):
        path = written(tmp_path)
        assert signoff.load(signoff.sidecar(path)).state(
            signoff.digest(signoff.read_record(path))
        ) == ("draft")

    def test_one_step_forward_at_a_time(self, tmp_path):
        path = written(tmp_path)
        with pytest.raises(UsageError, match="can go to for sign-off, not approved"):
            signoff.sign(path, state="approved", by="Erika Mustermann", at=AT)

    def test_the_whole_way_and_back_to_draft(self, tmp_path):
        path = written(tmp_path)
        for state in ("for sign-off", "approved", "published", "draft", "for sign-off"):
            signoff.sign(path, state=state, by="Erika Mustermann", at=AT)
        version = signoff.digest(signoff.read_record(path))
        assert signoff.load(signoff.sidecar(path)).state(version) == "for sign-off"

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
        assert main(["sign", str(path), "--as", "Erika Mustermann", "--state", "for sign-off"]) == 0
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
