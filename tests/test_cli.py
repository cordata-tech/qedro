"""The CLI, mostly to prove the mark rule holds end to end."""

import json

import pytest

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
