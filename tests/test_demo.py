"""The demo estate, and the acceptance criteria it exists to make runnable.

cordata-tech/qedro#2 asks for two things that cannot be checked without a
committed estate: that `qedro ropa ./demo` produces a valid Art. 30 record with
no Cordata infrastructure present, and that the same command against
runtime-declared events produces a *materially richer* one.

Both are asserted here rather than described. The three-tier progression —
lineage alone, lineage plus the mapping file, lineage that declares — is the
adoption story the README tells, so a change that quietly broke a tier would
otherwise only be caught by somebody reading the docs and trying it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook
from tools import seed

from qedro import TOMBSTONE
from qedro.__main__ import main

DEMO = Path("demo")
PLAIN = str(DEMO / "lineage")
DECLARED = str(DEMO / "lineage-declared")
CONFIG = str(DEMO / "qedro.yaml")


def record(*argv: str, capsys) -> dict:
    assert main(["ropa", *argv, "--format", "json"]) == 0
    return json.loads(capsys.readouterr().out)


class TestTheEstateIsThere:
    def test_both_estates_are_committed(self):
        # Without this the acceptance criteria in #2 are unrunnable, which is
        # the state they were in until the estate existed.
        for directory in (DEMO / "lineage", DEMO / "lineage-declared"):
            assert sorted(p.name for p in directory.glob("*.ndjson")) == [
                "airflow.ndjson",
                "dbt.ndjson",
                "spark.ndjson",
            ]

    def test_the_two_estates_differ_only_in_the_declaration(self):
        # The comparison in demo/README.md is only worth anything if the
        # estates are otherwise identical. Same jobs, same runs, same times.
        def skeleton(directory: Path) -> list[tuple[str, str, str]]:
            out = []
            for path in sorted(directory.glob("*.ndjson")):
                for line in path.read_text(encoding="utf-8").splitlines():
                    e = json.loads(line)
                    out.append((e["eventTime"], e["job"]["name"], e["run"]["runId"]))
            return sorted(out)

        assert skeleton(DEMO / "lineage") == skeleton(DEMO / "lineage-declared")

    def test_it_is_generated_rather_than_edited(self):
        # The same guard CI runs. A demo edited by hand drifts from the
        # generator and the next regeneration silently reverts the edit.
        for directory, files in seed.estates().items():
            for name, body in files.items():
                assert (DEMO / directory / name).read_text(encoding="utf-8") == body, (
                    f"demo/{directory}/{name} is out of date — run `python tools/seed.py`"
                )


class TestSourceNeutrality:
    """cordata-tech/qedro#2, and the first commitment in CLAUDE.md.

    The acceptance test is that the demo runs with *no AWS anywhere in the
    picture*. A demo estate that quietly carried LakeFormation tags would make
    the claim untestable while looking like it proved it.
    """

    @pytest.mark.parametrize("directory", ["lineage", "lineage-declared"])
    def test_nothing_in_the_estate_names_one_cloud(self, directory):
        forbidden = ("lf_tags", "lakeformation", "arn:aws", "amazonaws", "cordata://")
        for path in (DEMO / directory).glob("*.ndjson"):
            body = path.read_text(encoding="utf-8").lower()
            for term in forbidden:
                assert term not in body, f"{path} contains {term!r}"

    def test_the_emitters_are_the_ones_people_already_run(self):
        producers = set()
        for path in (DEMO / "lineage").glob("*.ndjson"):
            for line in path.read_text(encoding="utf-8").splitlines():
                producers.add(json.loads(line)["producer"])
        assert len(producers) == 3
        assert all("OpenLineage/OpenLineage" in p for p in producers)


class TestLineageAlone:
    """Tier one: what the tool can say from lineage and nothing else."""

    def test_it_finds_the_estate(self, capsys):
        payload = record(PLAIN, capsys=capsys)
        assert len(payload["activities"]) == 6
        assert payload["scope"]["events"] == 144

    def test_but_cannot_say_why_any_of_it_happened(self, capsys):
        payload = record(PLAIN, capsys=capsys)
        assert payload["scope"]["provenance"]["undeclared"] == 6
        assert payload["complete"] is False

    def test_and_says_that_the_controller_is_missing(self, capsys):
        payload = record(PLAIN, capsys=capsys)
        assert any("no controller is declared" in r for r in payload["reasons"])


class TestLineagePlusTheMappingFile:
    """Tier two: populated, readable, and honest about being asserted."""

    def test_the_record_is_populated(self, capsys):
        payload = record(PLAIN, "--config", CONFIG, capsys=capsys)
        assert payload["controller"]["name"] == "ACME Finanz GmbH"
        assert payload["scope"]["provenance"]["from_mapping"] == 5

    def test_every_filled_value_is_labelled_as_an_assertion(self, capsys):
        payload = record(PLAIN, "--config", CONFIG, capsys=capsys)
        filled = [a for a in payload["activities"] if a["purpose"]["value"]]
        assert filled
        assert all(a["purpose"]["provenance"] == "mapping" for a in filled)

    def test_the_job_the_mapping_file_forgot_is_named_not_hidden(self, capsys):
        # The demo's whole argument: a register kept by hand drifts, and the
        # drift is invisible unless something says it out loud.
        payload = record(PLAIN, "--config", CONFIG, capsys=capsys)
        [missed] = [a for a in payload["activities"] if not a["purpose"]["value"]]
        assert missed["job"] == "acme.crm/consent-sync"
        assert any("1 of 6 activities has no purpose" in r for r in payload["reasons"])

    def test_and_the_record_still_does_not_claim_to_be_a_proof(self, capsys):
        assert record(PLAIN, "--config", CONFIG, capsys=capsys)["complete"] is False


class TestLineageThatDeclares:
    """Tier three: the same estate, materially richer, and it earns the mark."""

    def test_every_activity_stands_on_emitted_evidence(self, capsys):
        payload = record(DECLARED, "--config", CONFIG, capsys=capsys)
        assert payload["scope"]["provenance"] == {
            "evidenced": 6,
            "from_mapping": 0,
            "undeclared": 0,
        }
        assert payload["complete"] is True
        assert payload["reasons"] == []

    def test_the_facet_beats_the_mapping_file_that_is_still_present(self, capsys):
        # The same config is passed. A facet always wins, so nothing in the
        # record is asserted even though the file could have supplied it.
        payload = record(DECLARED, "--config", CONFIG, capsys=capsys)
        assert all(a["purpose"]["provenance"] == "facet" for a in payload["activities"])

    def test_the_difference_from_tier_two_is_material_not_cosmetic(self, capsys):
        asserted = record(PLAIN, "--config", CONFIG, capsys=capsys)
        evidenced = record(DECLARED, "--config", CONFIG, capsys=capsys)

        assert [a["job"] for a in asserted["activities"]] == [
            a["job"] for a in evidenced["activities"]
        ]
        assert asserted["scope"]["events"] == evidenced["scope"]["events"]
        # Same estate, same jobs, same events — and one is a proof.
        assert asserted["complete"] is not evidenced["complete"]

    def test_the_mark_reaches_the_terminal(self, capsys):
        assert main(["ropa", DECLARED, "--config", CONFIG]) == 0
        assert TOMBSTONE in capsys.readouterr().out


class TestTheWholeThingAsAnAuditorReceivesIt:
    def test_a_workbook_from_the_demo(self, tmp_path, capsys):
        out = tmp_path / "acme-ropa.xlsx"
        assert main(["ropa", DECLARED, "--config", CONFIG, "--out", str(out)]) == 0
        assert TOMBSTONE in capsys.readouterr().out

        book = load_workbook(out)
        sheet = book["Art. 30 record"]
        assert sheet["A2"].value == "ACME Finanz GmbH"
        assert "stands on emitted evidence" in sheet["A4"].value
        # Six activities under one header row.
        assert sheet.max_row == 12
