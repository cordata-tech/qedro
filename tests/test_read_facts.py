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
from qedro.sources import ReadReport, read_dir, read_facts

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
