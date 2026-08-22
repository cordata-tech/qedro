"""The CLI, mostly to prove the mark rule holds end to end."""

import json

import pytest
from openpyxl import load_workbook

from qedro import TOMBSTONE, render
from qedro.__main__ import main

from .lineage_api import Backend, event

FIXTURES = "tests/fixtures/events"


def test_clean_read_earns_the_tombstone(capsys):
    assert main(["events", FIXTURES]) == 0
    out = capsys.readouterr().out
    assert "∎" in out
    assert "4 events" in out


def test_ascii_fallback_when_the_terminal_has_no_glyph(capsys):
    assert main(["events", FIXTURES, "--no-symbol"]) == 0
    out = capsys.readouterr().out
    assert "[complete]" in out
    assert "∎" not in out


def test_a_degraded_read_withholds_the_mark_and_says_why(tmp_path, capsys):
    good = json.dumps({"eventType": "COMPLETE", "run": {}, "job": {"namespace": "n", "name": "j"}})
    (tmp_path / "a.ndjson").write_text(f"{good}\n{{not json\n")
    assert main(["events", str(tmp_path)]) == 0
    cap = capsys.readouterr()
    assert "∎" not in cap.out
    assert "not usable OpenLineage events" in cap.err


def test_a_directory_that_yields_nothing_usable_fails(tmp_path, capsys):
    assert main(["events", str(tmp_path / "nope")]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_no_command_prints_help_and_fails(capsys):
    assert main([]) == 1
    assert "usage:" in capsys.readouterr().err


def test_the_flag_works_on_either_side_of_the_subcommand(capsys):
    # `qedro --no-symbol events ./` and `qedro events ./ --no-symbol` are both
    # how people type it. argparse makes the second one hard, so it is tested.
    assert main(["--no-symbol", "events", FIXTURES]) == 0
    assert "[complete]" in capsys.readouterr().out

    assert main(["events", FIXTURES, "--no-symbol"]) == 0
    assert "[complete]" in capsys.readouterr().out


def test_the_env_var_suppresses_the_glyph_for_ci_logs(capsys, monkeypatch):
    monkeypatch.setenv("QEDRO_NO_SYMBOL", "1")
    assert main(["events", FIXTURES]) == 0
    out = capsys.readouterr().out
    assert "[complete]" in out and "∎" not in out


def test_the_summary_says_file_not_files_when_there_is_one(capsys):
    assert main(["events", FIXTURES]) == 0
    assert "1 file" in capsys.readouterr().out


def test_an_empty_window_does_not_earn_the_mark(capsys):
    # A clean read of nothing is not a proof of anything, and the difference
    # between "nothing happened" and "nothing was recorded" is exactly what a
    # reviewer needs flagged.
    assert main(["events", FIXTURES, "--since", "2030-01-01"]) == 0
    cap = capsys.readouterr()
    assert "0 events" in cap.out
    assert "∎" not in cap.out
    assert "nothing was recorded" in cap.err


def test_a_window_narrows_the_read(capsys):
    assert main(["events", FIXTURES, "--since", "2026-08-13", "--until", "2026-08-14"]) == 0
    assert "4 events" in capsys.readouterr().out


def test_an_unparseable_date_is_rejected_with_a_usable_message(capsys):
    with pytest.raises(SystemExit):
        main(["events", FIXTURES, "--since", "yesterday"])
    assert "ISO-8601" in capsys.readouterr().err


def test_an_address_that_is_not_a_directory_or_http_says_so(capsys):
    # `s3:/bucket does not exist` would send someone looking for a typo.
    assert main(["events", "s3://bucket/lineage"]) == 2
    assert "only a directory or an http:// address" in capsys.readouterr().err


class TestAgainstAnApi:
    """The acceptance test for source-neutrality: no AWS anywhere in this."""

    def test_reads_a_lineage_api_end_to_end(self, serve, capsys):
        base = serve(Backend(events=[event(f"j{i}") for i in range(3)]))
        assert main(["events", base]) == 0
        out = capsys.readouterr().out
        assert "3 events" in out and "1 page" in out
        assert "∎" in out

    def test_a_backend_that_is_down_fails_rather_than_reporting_nothing(self, serve, capsys):
        base = serve(Backend(status=503))
        assert main(["events", base]) == 1
        assert "HTTP 503" in capsys.readouterr().err


class TestRopa:
    """The projection, through the CLI people actually type."""

    def test_it_writes_a_record(self, tmp_path, capsys):
        events = tmp_path / "events"
        events.mkdir()
        (events / "e.json").write_text(
            json.dumps(
                {
                    "eventType": "COMPLETE",
                    "eventTime": "2026-03-01T10:00:00Z",
                    "run": {"runId": "r"},
                    "job": {
                        "namespace": "acme.fraud",
                        "name": "scored",
                        "facets": {
                            "processing": {
                                "purpose": "fraud-detection",
                                "legal_basis": "legitimate-interest",
                            }
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        config = tmp_path / "qedro.yaml"
        config.write_text("controller: ACME GmbH\n", encoding="utf-8")

        out = tmp_path / "ropa.md"
        code = main(
            [
                "ropa",
                str(events),
                "--config",
                str(config),
                "--format",
                "markdown",
                "--out",
                str(out),
            ]
        )
        assert code == 0
        assert "ACME GmbH" in out.read_text(encoding="utf-8")
        assert "wrote" in capsys.readouterr().out

    def test_the_mark_reaches_the_summary_line_when_earned(self, tmp_path, capsys):
        events, config = _estate(tmp_path, facet=True)
        out = tmp_path / "r.json"
        assert main(["ropa", str(events), "--config", str(config), "--out", str(out)]) == 0
        assert TOMBSTONE in capsys.readouterr().out

    def test_and_is_withheld_with_the_reason_on_stderr(self, tmp_path, capsys):
        events, config = _estate(tmp_path, facet=False)
        out = tmp_path / "r.json"
        assert main(["ropa", str(events), "--config", str(config), "--out", str(out)]) == 0
        captured = capsys.readouterr()
        assert TOMBSTONE not in captured.out
        # The file is still written. The run succeeded; it just does not claim
        # to be a proof.
        assert out.exists()
        assert "!" in captured.err

    def test_a_bad_config_is_a_sentence_not_a_traceback(self, tmp_path, capsys):
        events, _ = _estate(tmp_path, facet=True)
        bad = tmp_path / "bad.yaml"
        bad.write_text('jobs:\n  "*": {legalbasis: consent}\n', encoding="utf-8")
        assert main(["ropa", str(events), "--config", str(bad)]) == 2
        assert "unknown keys" in capsys.readouterr().err

    def test_a_named_config_that_does_not_exist_says_so(self, tmp_path, capsys):
        events, _ = _estate(tmp_path, facet=True)
        assert main(["ropa", str(events), "--config", str(tmp_path / "nope.yaml")]) == 2
        assert "no config file at" in capsys.readouterr().err

    def test_every_format_is_reachable(self, tmp_path, capsys):
        # Driven off the registry rather than a list written here, so a format
        # added later cannot be unreachable from the CLI and still pass.
        events, config = _estate(tmp_path, facet=True)
        for fmt in sorted(render.names()):
            argv = ["ropa", str(events), "--config", str(config), "--format", fmt]
            if render.is_binary(fmt):
                out = tmp_path / f"record.{fmt}"
                assert main([*argv, "--out", str(out)]) == 0
                assert out.stat().st_size > 0
            else:
                assert main(argv) == 0
                assert capsys.readouterr().out.strip()


def _estate(tmp_path, *, facet: bool):
    """A one-job directory and a config, with or without the emitted facet."""
    events = tmp_path / "events"
    events.mkdir(exist_ok=True)
    job = {"namespace": "acme.fraud", "name": "scored", "facets": {}}
    if facet:
        job["facets"]["processing"] = {
            "purpose": "fraud-detection",
            "legal_basis": "legitimate-interest",
        }
    (events / "e.json").write_text(
        json.dumps(
            {
                "eventType": "COMPLETE",
                "eventTime": "2026-03-01T10:00:00Z",
                "run": {"runId": "r"},
                "job": job,
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "qedro.yaml"
    config.write_text("controller: ACME GmbH\n", encoding="utf-8")
    return events, config


class TestRopaAgainstAnApi:
    """The acceptance test for source-neutrality, on the projection this time.

    `qedro ropa` has to produce a record against a Marquez-compatible instance
    with **no AWS anywhere in the picture**. If this ever needs a LakeFormation
    client, a boto session or an AWS credential to pass, the tool has
    re-acquired the precondition that reading OpenLineage was supposed to
    remove.
    """

    def test_a_record_from_an_http_source(self, serve, tmp_path, capsys):
        emitted = event(job="scored")
        emitted["job"]["facets"] = {
            "processing": {
                "purpose": "fraud-detection",
                "legal_basis": "legitimate-interest",
            }
        }
        backend = Backend(events=[emitted])
        base = serve(backend)

        config = tmp_path / "qedro.yaml"
        config.write_text("controller: ACME GmbH\n", encoding="utf-8")

        assert main(["ropa", base, "--config", str(config), "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)

        assert payload["controller"]["name"] == "ACME GmbH"
        [activity] = payload["activities"]
        assert activity["purpose"]["provenance"] == "facet"
        assert payload["complete"] is True

        # Read-only by construction: the projection issued nothing but GETs.
        assert backend.methods == {"GET"}

    def test_the_scope_statement_names_the_instance(self, serve, tmp_path, capsys):
        # A record that does not say which instance it came from cannot be
        # reproduced by whoever receives it.
        base = serve(Backend(events=[event(job="scored")]))
        config = tmp_path / "qedro.yaml"
        config.write_text("controller: ACME GmbH\n", encoding="utf-8")

        assert main(["ropa", base, "--config", str(config), "--format", "json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["scope"]["source"] == base


class TestFormatFollowsTheFilename:
    def test_out_md_writes_markdown(self, tmp_path):
        events, config = _estate(tmp_path, facet=True)
        out = tmp_path / "ropa.md"
        assert main(["ropa", str(events), "--config", str(config), "--out", str(out)]) == 0
        assert out.read_text(encoding="utf-8").startswith("# Record of processing activities")

    def test_an_explicit_format_beats_the_filename(self, tmp_path):
        events, config = _estate(tmp_path, facet=True)
        out = tmp_path / "ropa.md"
        assert (
            main(
                [
                    "ropa",
                    str(events),
                    "--config",
                    str(config),
                    "--format",
                    "json",
                    "--out",
                    str(out),
                ]
            )
            == 0
        )
        json.loads(out.read_text(encoding="utf-8"))


class TestTheWorkbook:
    """xlsx is the one an auditor asks for, and the only output that is a file
    rather than something a terminal can show."""

    def test_out_xlsx_writes_a_workbook(self, tmp_path, capsys):
        events, config = _estate(tmp_path, facet=True)
        out = tmp_path / "ropa.xlsx"
        assert main(["ropa", str(events), "--config", str(config), "--out", str(out)]) == 0

        book = load_workbook(out)
        assert book.sheetnames == ["Art. 30 record", "Scope"]
        assert "wrote" in capsys.readouterr().out

    def test_asking_for_it_with_nowhere_to_put_it_is_a_sentence(self, tmp_path, capsys):
        events, config = _estate(tmp_path, facet=True)
        assert main(["ropa", str(events), "--config", str(config), "--format", "xlsx"]) == 2
        assert "add --out" in capsys.readouterr().err

    def test_that_failure_arrives_before_anything_is_read(self, capsys):
        # No source, no config, nothing that exists: the combination is
        # rejected on its own terms rather than after a long read.
        assert main(["ropa", "/nonexistent", "--format", "xlsx"]) == 2
        assert "add --out" in capsys.readouterr().err

    def test_the_mark_still_reaches_the_summary_line(self, tmp_path, capsys):
        events, config = _estate(tmp_path, facet=True)
        out = tmp_path / "ropa.xlsx"
        assert main(["ropa", str(events), "--config", str(config), "--out", str(out)]) == 0
        assert TOMBSTONE in capsys.readouterr().out
