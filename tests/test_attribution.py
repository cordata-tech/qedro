"""Why each change since a sign-off happened, as far as the events and files show (#49).

`qedro status --against` says what changed in a signed record; this is the cause
beside each change. The tests build a signed record and a fresh run from events,
as `status` does, and check the cause each kind of change is given — and that a
change nothing in front of qedro explains says so instead of being guessed.
"""

from __future__ import annotations

import json

from qedro import config, render, staleness, vocabulary
from qedro.attribution import (
    DECLARED,
    EMITTED,
    FIRST_RUN,
    MAPPING,
    STOPPED,
    UNATTRIBUTED,
    Attributor,
)
from qedro.events import parse_event
from qedro.ropa import build

WORDS = vocabulary.load()
CONTROLLER = "controller: ACME GmbH\n"
COMMIT = "4f2a9c1e8b7d6a5f4e3d2c1b0a9f8e7d6c5b4a39"


def event(
    run,
    when,
    *,
    name="scored",
    purpose=None,
    basis="legitimate-interest",
    reads=("wh/raw.customers",),
    commit=None,
):
    raw = {
        "eventType": "COMPLETE",
        "eventTime": when,
        "run": {"runId": run},
        "job": {"namespace": "acme.fraud", "name": name, "facets": {}},
        "inputs": [{"namespace": k.split("/")[0], "name": k.split("/")[1]} for k in reads],
        "outputs": [{"namespace": "wh", "name": "curated.scores"}],
    }
    if purpose:
        raw["job"]["facets"]["processing"] = {"purpose": purpose, "legal_basis": basis}
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


def record(events, cfg=""):
    return build(
        events, config=config.parse(CONTROLLER + cfg, origin="qedro.yaml"), vocabulary=WORDS
    )


def checked(signed_events, fresh_events, *, signed_cfg="", fresh_cfg=""):
    signed = json.loads(render.FORMATS["json"](record(signed_events, signed_cfg)))
    fresh_record = record(fresh_events, fresh_cfg)
    fresh = json.loads(render.FORMATS["json"](fresh_record))
    return staleness.check(
        signed, fresh, origin="ropa.json", attributor=Attributor(fresh_record, fresh_events)
    )


def causes(result, key="acme.fraud/scored"):
    [state] = [a for a in result.activities if a.key == key]
    return {c.label: cause for c, cause in zip(state.changes, state.causes, strict=True)}


SIGNED = [event("r0", "2026-03-01T10:00:00Z", purpose="fraud-detection")]


class TestAFacetChange:
    def test_names_the_first_run_that_emitted_the_new_value_and_its_commit(self):
        fresh = [
            # A run that emitted no facet, then the one that changed it.
            event("r1", "2026-03-10T10:00:00Z"),
            event("r2", "2026-03-11T10:00:00Z", purpose="chargeback-handling", commit=COMMIT),
            event("r3", "2026-03-12T10:00:00Z", purpose="chargeback-handling", commit=COMMIT),
        ]
        cause = causes(checked(SIGNED, fresh))["purpose"]
        assert cause.cause == EMITTED
        assert (cause.run, cause.commit) == ("r2", COMMIT)
        assert cause.says == (
            "first emitted as chargeback-handling by run r2 on 2026-03-11, at commit "
            "4f2a9c1e8b7d of https://github.com/acme/pipelines/jobs/scored.py"
        )

    def test_says_the_change_may_be_older_than_the_window_when_the_first_run_has_it(self):
        fresh = [event("r1", "2026-03-10T10:00:00Z", purpose="chargeback-handling")]
        cause = causes(checked(SIGNED, fresh))["purpose"]
        assert cause.cause == EMITTED
        assert cause.says.endswith(
            "; the run names no commit — the job's first run in the window, "
            "so it may be older than the window"
        )


class TestAMappingChange:
    RULE = '\njobs:\n  "acme.fraud/*":\n    purpose: {purpose}\n    legal_basis: contract\n'

    def test_names_the_rule_now_supplying_the_value_with_its_file_and_line(self):
        events = [event("r1", "2026-03-10T10:00:00Z")]
        result = checked(
            events,
            events,
            signed_cfg=self.RULE.format(purpose="fraud-detection"),
            fresh_cfg=self.RULE.format(purpose="chargeback-handling"),
        )
        cause = causes(result)["purpose"]
        assert cause.cause == MAPPING
        assert (cause.rule, cause.file, cause.line) == ("acme.fraud/*", "qedro.yaml", 4)
        assert cause.says == "supplied by the rule `acme.fraud/*` in qedro.yaml line 4"

    def test_says_when_emission_stopped_and_a_rule_took_over(self):
        fresh = [event("r1", "2026-03-10T10:00:00Z")]
        result = checked(SIGNED, fresh, fresh_cfg=self.RULE.format(purpose="fraud-detection"))
        cause = causes(result)["purpose"]
        assert cause.cause == MAPPING
        assert cause.says.startswith("no run in the window emitted a purpose; now supplied by")


class TestOtherChanges:
    def test_a_value_nothing_supplies_any_more_is_stopped_not_explained(self):
        fresh = [event("r1", "2026-03-10T10:00:00Z")]
        cause = causes(checked(SIGNED, fresh))["purpose"]
        assert cause.cause == STOPPED
        assert "what stopped it is not in the events" in cause.says

    def test_a_dataset_newly_read_names_the_first_run_that_read_it(self):
        fresh = [
            event("r1", "2026-03-10T10:00:00Z", purpose="fraud-detection"),
            event(
                "r2",
                "2026-03-11T10:00:00Z",
                purpose="fraud-detection",
                reads=("wh/raw.customers", "wh/raw.devices"),
                commit=COMMIT,
            ),
        ]
        cause = causes(checked(SIGNED, fresh))["reads"]
        assert (cause.cause, cause.run, cause.commit) == (FIRST_RUN, "r2", COMMIT)
        assert cause.says.startswith("first read by run r2 on 2026-03-11")

    def test_a_new_activity_names_its_first_run(self):
        fresh = [
            event("r1", "2026-03-10T10:00:00Z", purpose="fraud-detection"),
            event("n1", "2026-03-11T10:00:00Z", name="segments", purpose="fraud-detection"),
        ]
        [new] = [a for a in checked(SIGNED, fresh).activities if a.state == staleness.NEW]
        assert new.cause is not None
        assert (new.cause.cause, new.cause.run) == (FIRST_RUN, "n1")

    def test_a_kind_of_change_not_traced_yet_says_so_and_why(self):
        # A classification comes from dataset tags any event can carry; this slice
        # does not trace it, and says that rather than naming a cause.
        def tagged(run, when, value):
            raw = {
                "eventType": "COMPLETE",
                "eventTime": when,
                "run": {"runId": run},
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
                "inputs": [],
                "outputs": [
                    {
                        "namespace": "wh",
                        "name": "curated.scores",
                        "facets": {
                            "tags": {
                                "tags": [{"key": "data_category", "value": value, "source": "T"}]
                            }
                        },
                    }
                ],
            }
            return parse_event(raw)

        result = checked(
            [tagged("r0", "2026-03-01T10:00:00Z", "contact")],
            [tagged("r1", "2026-03-10T10:00:00Z", "financial")],
        )
        cause = causes(result)["data_category"]
        assert cause.cause == UNATTRIBUTED
        assert "does not trace this kind of change" in cause.says


def test_a_declared_activity_is_attributed_to_its_document_never_to_events():
    from qedro.attribution import attribute
    from qedro.compare import CHANGED, Change, Value
    from qedro.ropa import Provenance

    change = Change(
        entry="support-reply-drafts",
        kind=CHANGED,
        entry_kind="declared",
        field="purpose",
        before=Value("customer-support", Provenance.DECLARED),
        after=Value("marketing", Provenance.DECLARED),
    )
    cause = attribute(change, None, [])
    assert cause.cause == DECLARED
    assert "no event can show when it changed" in cause.says


def test_the_json_carries_each_cause_beside_its_change():
    fresh = [event("r1", "2026-03-10T10:00:00Z", purpose="chargeback-handling", commit=COMMIT)]
    payload = staleness.check_json(checked(SIGNED, fresh))
    [scored] = [a for a in payload["activities"] if a["key"] == "acme.fraud/scored"]
    [purpose] = [c for c in scored["changes"] if c["field"] == "purpose"]
    assert purpose["cause"]["cause"] == "emitted"
    assert purpose["cause"]["run"] == "r1"
    assert purpose["cause"]["commit"] == COMMIT
    assert purpose["cause"]["rule"] is None


def test_without_an_attributor_nothing_changes_but_the_causes_are_absent():
    # The comparison is the same with or without attribution; only the cause goes.
    signed = json.loads(render.FORMATS["json"](record(SIGNED)))
    fresh = json.loads(
        render.FORMATS["json"](
            record([event("r1", "2026-03-10T10:00:00Z", purpose="chargeback-handling")])
        )
    )
    plain = staleness.check(signed, fresh, origin="ropa.json")
    assert all(a.causes == () for a in plain.activities)
    payload = staleness.check_json(plain)
    assert all(c["cause"] is None for a in payload["activities"] for c in a["changes"])
