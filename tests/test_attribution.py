"""Why each change since a sign-off happened, as far as the events and files show (#49).

`qedro status --against` says what changed in a signed record; this is the cause
beside each change. The tests build a signed record from the events up to a
boundary and a fresh run from all of them, as `status` reads a source, and check
the cause each kind of change is given: before → after the boundary where the
events hold both sides, and *unattributed* or *may be older* where they do not.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from qedro import config, history, render, staleness, vocabulary
from qedro.attribution import (
    DECLARED,
    EMITTED,
    FIRST_RUN,
    MAPPING,
    STOPPED,
    TAGGED,
    Attributor,
    Context,
    attribute,
)
from qedro.compare import CHANGED, Change, Value
from qedro.events import parse_event
from qedro.ropa import Provenance, build

WORDS = vocabulary.load()
CONTROLLER = "controller: ACME GmbH\n"
C0 = "0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a"
C1 = "4f2a9c1e8b7d6a5f4e3d2c1b0a9f8e7d6c5b4a39"


def dataset(key, tags=None):
    namespace, _, name = key.partition("/")
    out = {"namespace": namespace, "name": name}
    if tags:
        out["facets"] = {
            "tags": {"tags": [{"key": k, "value": v, "source": "T"} for k, v in tags.items()]}
        }
    return out


def event(
    run,
    when,
    *,
    job="acme.fraud/scored",
    purpose=None,
    reads=("wh/raw.customers",),
    writes=("wh/curated.scores",),
    commit=None,
    tags=None,
):
    """One COMPLETE event. *tags* is `{dataset: {key: value}}` for its datasets."""
    tags = tags or {}
    namespace, _, name = job.partition("/")
    raw = {
        "eventType": "COMPLETE",
        "eventTime": when,
        "run": {"runId": run},
        "job": {"namespace": namespace, "name": name, "facets": {}},
        "inputs": [dataset(k, tags.get(k)) for k in reads],
        "outputs": [dataset(k, tags.get(k)) for k in writes],
    }
    if purpose:
        raw["job"]["facets"]["processing"] = {
            "purpose": purpose,
            "legal_basis": "legitimate-interest",
        }
    if commit:
        raw["job"]["facets"]["sourceCodeLocation"] = {
            "type": "git",
            "url": "https://github.com/acme/pipelines",
            "path": "jobs/scored.py",
            "version": commit,
        }
    parsed = parse_event(raw)
    assert parsed is not None
    return parsed


def record(events, cfg="", origin="qedro.yaml"):
    return build(events, config=config.parse(CONTROLLER + cfg, origin=origin), vocabulary=WORDS)


def checked(signed_events, fresh_events, *, signed_cfg="", fresh_cfg="", origin="qedro.yaml"):
    """A record signed over *signed_events*, checked against a fresh run over
    *fresh_events*, which as `status` reads a source include the signed ones."""
    signed = json.loads(render.FORMATS["json"](record(signed_events, signed_cfg, origin)))
    fresh_record = record(fresh_events, fresh_cfg, origin)
    fresh = json.loads(render.FORMATS["json"](fresh_record))
    return staleness.check(
        signed, fresh, origin="ropa.json", attributor=Attributor(fresh_record, fresh_events)
    )


def causes(result, key="acme.fraud/scored"):
    [state] = [a for a in result.activities if a.key == key]
    return {
        (c.label, str(c.after or c.before)): cause
        for c, cause in zip(state.changes, state.causes, strict=True)
    }


def cause_of(result, label, key="acme.fraud/scored"):
    [found] = [v for (lab, _), v in causes(result, key).items() if lab == label]
    return found


class TestAFacetChange:
    def test_names_the_run_and_commit_that_emitted_it_and_the_job_before(self):
        # Before the sign-off the job ran with no processing facet; after it, a
        # run at a new commit started emitting a purpose.
        signed = [event("r0", "2026-03-01T10:00:00Z", commit=C0)]
        fresh = [
            *signed,
            event("r1", "2026-03-10T10:00:00Z", commit=C0),
            event("r2", "2026-03-11T10:00:00Z", purpose="chargeback-handling", commit=C1),
        ]
        cause = cause_of(checked(signed, fresh), "purpose")
        assert cause.cause == EMITTED
        assert (cause.run, cause.commit, cause.commit_before) == ("r2", C1, C0)
        assert cause.says == (
            "first emitted as chargeback-handling by run r2 on 2026-03-11, at commit "
            "4f2a9c1e8b7d of https://github.com/acme/pipelines/jobs/scored.py; the job's "
            "last run before the sign-off, r0 on 2026-03-01, ran at commit 0a0a0a0a0a0a"
        )

    def test_says_it_may_be_older_when_the_events_hold_nothing_before(self):
        signed = [event("r0", "2026-03-01T10:00:00Z", purpose="fraud-detection")]
        fresh = [event("r1", "2026-03-10T10:00:00Z", purpose="chargeback-handling")]
        cause = cause_of(checked(signed, fresh), "purpose")
        assert cause.cause == EMITTED
        assert cause.says.endswith(
            "; the job has no run before the sign-off in the events, so it may be older"
        )


RULE = '\njobs:\n  "acme.fraud/*":\n    purpose: {purpose}\n    legal_basis: contract\n'


class TestAMappingChange:
    def test_names_the_rule_now_supplying_the_value_with_its_file_and_line(self):
        events = [event("r1", "2026-03-01T10:00:00Z")]
        result = checked(
            events,
            events,
            signed_cfg=RULE.format(purpose="fraud-detection"),
            fresh_cfg=RULE.format(purpose="chargeback-handling"),
        )
        cause = cause_of(result, "purpose")
        assert cause.cause == MAPPING
        assert (cause.rule, cause.file, cause.line) == ("acme.fraud/*", "qedro.yaml", 4)
        assert cause.says.startswith("supplied by the rule `acme.fraud/*` in qedro.yaml line 4")

    def test_says_when_emission_stopped_and_a_rule_took_over(self):
        signed = [event("r0", "2026-03-01T10:00:00Z", purpose="fraud-detection")]
        fresh = [event("r1", "2026-03-10T10:00:00Z")]
        cause = cause_of(
            checked(signed, fresh, fresh_cfg=RULE.format(purpose="fraud-detection")), "purpose"
        )
        assert cause.cause == MAPPING
        assert cause.says.startswith("no run in the window emitted a purpose; now supplied by")


git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def repository(tmp_path, *versions):
    """A Git repository holding qedro.yaml, one commit per version of its text."""

    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.name", "Erika Mustermann")
    run("config", "user.email", "erika@acme.example")
    run("config", "commit.gpgsign", "false")
    path = tmp_path / "qedro.yaml"
    for i, text in enumerate(versions):
        path.write_text(text)
        run("add", "qedro.yaml")
        run("commit", "-q", "-m", f"change {i}")
    return path


@git
class TestTheRulesHistory:
    def test_names_the_commit_that_last_changed_the_rule_and_who_made_it(self, tmp_path):
        history.line_change.cache_clear()
        path = repository(
            tmp_path,
            CONTROLLER + RULE.format(purpose="fraud-detection"),
            CONTROLLER + RULE.format(purpose="chargeback-handling"),
        )
        events = [event("r1", "2026-03-01T10:00:00Z")]
        result = checked(
            events,
            events,
            signed_cfg=RULE.format(purpose="fraud-detection"),
            fresh_cfg=RULE.format(purpose="chargeback-handling"),
            origin=str(path),
        )
        cause = cause_of(result, "purpose")
        assert cause.rule_change is not None
        # The commit that changed the purpose under the pattern, not the one that
        # wrote the pattern: the rule's whole block is read.
        assert cause.rule_change.subject == "change 1"
        assert cause.rule_change.author == "Erika Mustermann"
        assert ", last changed in commit " in cause.says
        assert cause.says.endswith(": change 1")

    def test_an_uncommitted_change_is_said_rather_than_read_past(self, tmp_path):
        history.line_change.cache_clear()
        path = repository(tmp_path, CONTROLLER + RULE.format(purpose="fraud-detection"))
        path.write_text(CONTROLLER + RULE.format(purpose="chargeback-handling"))
        found = history.line_change(str(path), 4, 6)
        assert isinstance(found, history.Unavailable)
        assert "uncommitted changes" in found.reason

    def test_a_file_outside_a_repository_says_so(self, tmp_path):
        history.line_change.cache_clear()
        path = tmp_path / "qedro.yaml"
        path.write_text(CONTROLLER + RULE.format(purpose="x"))
        found = history.line_change(str(path), 4)
        assert isinstance(found, history.Unavailable)
        assert "not in a Git repository" in found.reason

    def test_a_rules_block_runs_to_the_next_entry_at_its_indent(self, tmp_path):
        path = tmp_path / "q.yaml"
        path.write_text('jobs:\n  "a/*":\n    purpose: p\n\n    legal_basis: c\n  "b/*":\n')
        assert history.block_end(str(path), 2) == 5


class TestAnUpstreamChange:
    def test_shows_each_level_of_the_chain_before_and_after_the_sign_off(self):
        # Signed: scored reads customers. After: it also reads devices, written by
        # a job new since the sign-off that reads src/d; src/d is written by ingest,
        # which ran before at C0 and after at C1, now also reading src/x.
        signed = [
            event("i0", "2026-02-28T10:00:00Z", job="acme.raw/ingest", reads=("src/a",),
                  writes=("src/d",), commit=C0, purpose="fraud-detection"),
            event("r0", "2026-03-01T10:00:00Z", purpose="fraud-detection"),
        ]  # fmt: skip
        fresh = [
            *signed,
            event("i1", "2026-03-05T10:00:00Z", job="acme.raw/ingest", reads=("src/a", "src/x"),
                  writes=("src/d",), commit=C1, purpose="fraud-detection"),
            event("d1", "2026-03-06T10:00:00Z", job="acme.raw/devices", reads=("src/d",),
                  writes=("wh/raw.devices",), purpose="fraud-detection"),
            event("r1", "2026-03-07T10:00:00Z", purpose="fraud-detection",
                  reads=("wh/raw.customers", "wh/raw.devices")),
        ]  # fmt: skip
        cause = cause_of(checked(signed, fresh), "reads")
        assert (cause.cause, cause.run) == (FIRST_RUN, "r1")
        devices, ingest = cause.upstream
        assert (devices.dataset, devices.job, devices.new) == (
            "wh/raw.devices",
            "acme.raw/devices",
            True,
        )
        assert (ingest.dataset, ingest.job, ingest.new) == ("src/d", "acme.raw/ingest", False)
        assert (ingest.commit_before, ingest.commit_after) == (C0, C1)
        assert ingest.inputs_gained == ("src/x",)
        assert cause.says.endswith(
            "; upstream: wh/raw.devices is written by acme.raw/devices, which has no run "
            "before the sign-off in the events; src/d is written by acme.raw/ingest "
            "(commit 0a0a0a0a0a0a → 4f2a9c1e8b7d; now also reading src/x)"
        )

    def test_a_producer_unchanged_since_the_sign_off_says_so_and_the_walk_stops(self):
        signed = [
            event("p0", "2026-02-28T10:00:00Z", job="acme.raw/devices", reads=("src/d",),
                  writes=("wh/raw.devices",), purpose="fraud-detection"),
            event("r0", "2026-03-01T10:00:00Z", purpose="fraud-detection"),
        ]  # fmt: skip
        fresh = [
            *signed,
            event("p1", "2026-03-05T10:00:00Z", job="acme.raw/devices", reads=("src/d",),
                  writes=("wh/raw.devices",), purpose="fraud-detection"),
            event("r1", "2026-03-07T10:00:00Z", purpose="fraud-detection",
                  reads=("wh/raw.customers", "wh/raw.devices")),
        ]  # fmt: skip
        [step] = cause_of(checked(signed, fresh), "reads").upstream
        assert not step.changed
        assert step.says() == (
            "wh/raw.devices is written by acme.raw/devices, unchanged since the sign-off"
        )


class TestAClassificationChange:
    def test_names_the_run_whose_event_first_tagged_the_dataset_and_its_job(self):
        signed = [event("r0", "2026-03-01T10:00:00Z", purpose="fraud-detection")]
        fresh = [
            *signed,
            # A catalog sync, a job of its own, tags the table the activity writes.
            event("t1", "2026-03-04T10:00:00Z", job="acme.catalog/sync",
                  reads=("wh/curated.scores",), writes=(), commit=C1,
                  tags={"wh/curated.scores": {"data_category": "financial"}}),
            event("r1", "2026-03-05T10:00:00Z", purpose="fraud-detection"),
        ]  # fmt: skip
        cause = cause_of(checked(signed, fresh), "data_category")
        assert (cause.cause, cause.run, cause.job) == (TAGGED, "t1", "acme.catalog/sync")
        # The other job is named beside its run, so "the job" after it is that one.
        assert cause.says.startswith(
            "first tagged data_category financial on wh/curated.scores by run t1 of "
            "acme.catalog/sync on 2026-03-04, at commit 4f2a9c1e8b7d"
        )
        assert cause.says.endswith(
            "; the job has no run before the sign-off in the events, so it may be older"
        )


class TestOtherChanges:
    def test_a_value_nothing_supplies_any_more_is_stopped_not_explained(self):
        signed = [event("r0", "2026-03-01T10:00:00Z", purpose="fraud-detection")]
        fresh = [event("r1", "2026-03-10T10:00:00Z")]
        cause = cause_of(checked(signed, fresh), "purpose")
        assert cause.cause == STOPPED
        assert "what stopped it is not in the events" in cause.says

    def test_a_new_activity_names_its_first_run_after_the_sign_off(self):
        signed = [event("r0", "2026-03-01T10:00:00Z", purpose="fraud-detection")]
        fresh = [
            *signed,
            event("n1", "2026-03-11T10:00:00Z", job="acme.fraud/segments",
                  purpose="fraud-detection"),
        ]  # fmt: skip
        [new] = [a for a in checked(signed, fresh).activities if a.state == staleness.NEW]
        assert new.cause is not None
        assert (new.cause.cause, new.cause.run) == (FIRST_RUN, "n1")
        assert new.cause.says.startswith("first ran as run n1 on 2026-03-11")


def test_a_declared_activity_is_attributed_to_its_document_never_to_events():
    change = Change(
        entry="support-reply-drafts",
        kind=CHANGED,
        entry_kind="declared",
        field="purpose",
        before=Value("customer-support", Provenance.DECLARED),
        after=Value("marketing", Provenance.DECLARED),
    )
    cause = attribute(change, None, Context([], None))
    assert cause.cause == DECLARED
    assert "no event can show when it changed" in cause.says


def test_the_json_carries_each_cause_with_the_chain_beside_its_change():
    signed = [event("r0", "2026-03-01T10:00:00Z", commit=C0)]
    fresh = [
        *signed,
        event("r2", "2026-03-11T10:00:00Z", purpose="chargeback-handling", commit=C1),
    ]
    payload = staleness.check_json(checked(signed, fresh))
    [scored] = [a for a in payload["activities"] if a["key"] == "acme.fraud/scored"]
    [purpose] = [c for c in scored["changes"] if c["field"] == "purpose"]
    assert purpose["cause"]["cause"] == "emitted"
    assert (purpose["cause"]["commit"], purpose["cause"]["commit_before"]) == (C1, C0)
    assert purpose["cause"]["upstream"] == []
    assert purpose["cause"]["rule_change"] is None


def test_without_an_attributor_nothing_changes_but_the_causes_are_absent():
    signed = json.loads(
        render.FORMATS["json"](
            record([event("r0", "2026-03-01T10:00:00Z", purpose="fraud-detection")])
        )
    )
    fresh = json.loads(
        render.FORMATS["json"](
            record([event("r1", "2026-03-10T10:00:00Z", purpose="chargeback-handling")])
        )
    )
    plain = staleness.check(signed, fresh, origin="ropa.json")
    assert all(a.causes == () for a in plain.activities)
    payload = staleness.check_json(plain)
    assert all(c["cause"] is None for a in payload["activities"] for c in a["changes"])
