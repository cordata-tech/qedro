"""What the read found, in every projection's JSON (#57).

A pilot's first question is whether its lineage is arriving. The JSON's
`scope.read` answers it from the read report and the events, so the console's
Sources page can show it without working anything out itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qedro import config, deployer, erasure, provenance, quality, render, ropa, signoff, vocabulary
from qedro.sources import ReadReport, read, read_dir, read_facts

DBT = Path(__file__).parent / "fixtures" / "dbt-1.53"
DATASET = "duckdb://probe.duckdb/probe.main.orders_explicit"
CFG = config.parse("controller: ACME GmbH\ndomains: [dbt, fraud]\n")


def build(projection: str):
    events, report = read_dir(DBT)
    if projection == "ropa":
        return ropa.build(events, config=CFG, vocabulary=vocabulary.load(), report=report)
    if projection == "deployer":
        record = ropa.build(events, config=CFG, vocabulary=vocabulary.load(), report=report)
        return deployer.build(record, events, report=report)
    if projection == "quality":
        return quality.build(events, config=CFG, report=report)
    if projection == "provenance":
        return provenance.build(events, dataset=DATASET, config=CFG, report=report)
    return erasure.build(events, dataset=DATASET, config=CFG, report=report)


@pytest.mark.parametrize("projection", ["ropa", "deployer", "quality", "provenance", "erasure"])
def test_every_projection_says_what_the_read_found(projection):
    read = json.loads(render.json(build(projection)))["scope"]["read"]
    assert read["source"] == str(DBT)
    assert read["kind"] == "directory"
    assert (read["files"], read["events"], read["skipped_records"]) == (1, 10, 0)
    assert read["passed_over"] == ["README.md"]
    assert read["earliest"] == "2026-09-08T10:52:40.065598+00:00"
    assert read["latest"] == "2026-09-08T10:52:44.996611+00:00"


def test_a_declared_domain_that_produced_nothing_is_listed_at_zero():
    # dbt's two invocation events belong to an orchestration parent (#8), so the
    # domain counts the eight events of its models.
    read = json.loads(render.json(build("ropa")))["scope"]["read"]
    assert read["domains"] == {"dbt": 8, "fraud": 0}


@pytest.mark.parametrize(
    ("origin", "kind"),
    [
        ("tests/fixtures/dbt-1.53", "directory"),
        ("http://marquez:5000", "api"),
        ("https://lineage.example.internal", "api"),
        ("s3://bucket/openlineage/", "bucket"),
        ("gs://bucket/openlineage/", "bucket"),
    ],
)
def test_the_kind_of_source_is_named_as_read_decides_it(origin, kind):
    facts = read_facts(ReadReport(origin=origin), [])
    assert facts is not None and facts.kind == kind


def test_events_that_did_not_come_from_a_read_carry_no_read_block():
    events, _ = read_dir(DBT)
    record = ropa.build(events, config=CFG, vocabulary=vocabulary.load())
    assert json.loads(render.json(record))["scope"]["read"] is None


def test_the_read_block_is_outside_what_a_sign_off_covers():
    # A record rebuilt a day later reads more events; that is no reason to reopen
    # an approval, so changing every field of `read` must leave the hash alone.
    payload = json.loads(render.json(build("ropa")))
    before = signoff.digest(payload)
    payload["scope"]["read"] = {"events": 999, "domains": {"fraud": 7}}
    assert signoff.digest(payload) == before


LAB = Path(__file__).parent / "fixtures" / "qedro-lab-airflow-3.4"


def with_copies(tmp_path, copies=3):
    """The lab's capture with its first *copies* events stored again, as Marquez did."""
    lines = (LAB / "events.jsonl").read_text().splitlines()
    (tmp_path / "events.jsonl").write_text("\n".join(lines + lines[:copies]) + "\n")
    return tmp_path


def lab_build(projection, source):
    # read(), the one entry point every command uses, which is where copies are counted.
    events, report = read(str(source))
    if projection == "ropa":
        return ropa.build(events, config=CFG, vocabulary=vocabulary.load(), report=report)
    if projection == "quality":
        return quality.build(events, config=CFG, report=report)
    target = "postgres://warehouse:5432/acme.marts.crm_customers"
    if projection == "provenance":
        return provenance.build(events, dataset=target, config=CFG, report=report)
    return erasure.build(events, dataset=target, config=CFG, report=report)


@pytest.mark.parametrize("projection", ["ropa", "quality", "provenance", "erasure"])
def test_copies_a_backend_stored_leave_every_artefact_as_it_was(projection, tmp_path):
    # #58: the lab's Marquez held three events twice. Counted once, every projection
    # says what it said without them, apart from the count of what was set aside.
    clean = json.loads(render.json(lab_build(projection, LAB)))
    copied = json.loads(render.json(lab_build(projection, with_copies(tmp_path))))
    assert copied["scope"]["duplicates"] == 3
    for payload in (clean, copied):
        payload["scope"].pop("read")
        payload["scope"].pop("duplicates")
        payload["scope"].pop("source", None)
        payload["scope"].pop("passed_over")  # the copy directory has no README to pass over
        payload["scope"].pop("statement")  # states the copies and the README, as it should
    assert copied == clean


@pytest.mark.parametrize("fmt", ["text", "markdown", "json", "pdf", "xlsx"])
def test_every_format_names_the_copies_counted_once(fmt, tmp_path):
    from .as_text import as_text

    record = lab_build("ropa", with_copies(tmp_path))
    out = as_text(render.FORMATS[fmt](record))
    if fmt == "json":
        assert json.loads(out)["scope"]["duplicates"] == 3
    else:
        assert "3 records identical to one already read, counted once" in out


class TestTheScopeStatementInTheJson:
    """The rows the text format prints, carried in the JSON for a human reader (#61)."""

    @pytest.mark.parametrize("projection", ["ropa", "deployer", "quality", "provenance", "erasure"])
    def test_it_is_every_row_the_text_format_prints_in_its_order(self, projection):
        record = build(projection)
        rows = json.loads(render.json(record))["scope"]["statement"]
        text = render.text(record)
        assert rows[0] == {"label": "source", "text": str(DBT)}
        assert rows[1]["label"] == "window"
        section = text[text.rindex("  Scope of this") :]
        positions = [section.index(f"    {row['label']} ") for row in rows]
        assert positions == sorted(positions), "the JSON's order is the text format's"
        for row in rows:
            first_words = " ".join(row["text"].split()[:3])
            assert first_words in " ".join(section.split()), row

    def test_files_passed_over_a_guessed_domain_and_copies_each_have_a_row(self, tmp_path):
        source = with_copies(tmp_path)
        (source / "README.md").write_text("notes beside the events\n")
        rows = json.loads(render.json(lab_build("ropa", source)))["scope"]["statement"]
        labels = {row["label"]: row["text"] for row in rows}
        assert labels["passed over"].startswith("1 file not read")
        assert labels["duplicates"] == "3 records identical to one already read, counted once"
        assert "guessed from the job namespace" in labels["domains"]

    def test_it_is_outside_what_a_sign_off_covers(self):
        payload = json.loads(render.json(build("ropa")))
        before = signoff.digest(payload)
        payload["scope"]["statement"] = [{"label": "anything", "text": "else"}]
        assert signoff.digest(payload) == before
