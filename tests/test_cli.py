"""The CLI, mostly to prove the mark rule holds end to end."""

import json

from qedro.__main__ import main

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
