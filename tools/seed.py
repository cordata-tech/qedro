"""Generates the demo estate in `demo/`.

Client lineage cannot be used and a three-event toy proves nothing, so the
thing `qedro ropa` is demonstrated against has to be invented — and invented
well enough that the record it produces reads like one somebody would actually
hand to a supervisory authority. cordata-tech/qedro#2 warns against budgeting
this as an afterthought. It was right to.

Two estates, from the same fictional company:

``demo/lineage``
    What most organisations have today. dbt, Airflow and Spark emitting
    OpenLineage, with no Art. 30 facet anywhere, because nothing standard asks
    them for one.

``demo/lineage-declared``
    The same fourteen days after the pipelines were taught to declare their
    purpose and lawful basis. Identical jobs, identical datasets, identical
    runs — the *only* difference is the ``processing`` job facet.

That pairing is the demonstration. Run the projection against each and the
difference is not cosmetic: the first record is asserted, the second is
evidenced, and only the second earns the mark.

**Everything here is deterministic.** No randomness, no clock — run IDs are
UUIDv5 over the job and the day, and every timestamp derives from `START`. Two
runs of this script produce byte-identical files, so a diff in `demo/` is
always a real change to the estate and never noise.

Usage::

    python tools/seed.py            # rewrite demo/
    python tools/seed.py --check    # fail if demo/ is out of date
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"

#: A company that does not exist, in a sector where the record matters.
CONTROLLER = "ACME Finanz GmbH"

#: Fourteen days is enough for run counts to look like a schedule rather than
#: a sample, and short enough that the committed estate stays a few hundred
#: kilobytes.
START = datetime(2026, 6, 1, tzinfo=UTC)
DAYS = 14

#: Real OpenLineage producer strings. The integrations are named because the
#: whole claim is that this works against what people already run — an estate
#: whose events all came from one emitter would not demonstrate that.
EMITTERS = {
    "dbt": "https://github.com/OpenLineage/OpenLineage/tree/1.24.2/integration/dbt",
    "airflow": "https://github.com/OpenLineage/OpenLineage/tree/1.24.2/integration/airflow",
    "spark": "https://github.com/OpenLineage/OpenLineage/tree/1.24.2/integration/spark",
}

SPEC = "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent"
FACET_SPEC = "https://openlineage.io/spec/facets/1-2-0"

#: The Art. 30 facet as this repository publishes it. Matches the `$id` in
#: `schemas/openlineage-art30-processing-facet.json`.
PROCESSING_SCHEMA = (
    "https://github.com/cordata-tech/qedro/blob/main/"
    "schemas/openlineage-art30-processing-facet.json"
)

#: Columns, so the datasets in the record look like tables somebody would have
#: to answer for. The personal data is the point: an Art. 30 record about
#: `table_a` and `table_b` demonstrates nothing.
SCHEMAS: dict[str, list[tuple[str, str]]] = {
    "fraud_raw.transactions": [
        ("tx_id", "VARCHAR"),
        ("account_id", "VARCHAR"),
        ("iban", "VARCHAR"),
        ("amount_eur", "DOUBLE"),
        ("merchant_id", "VARCHAR"),
        ("booked_at", "TIMESTAMP"),
    ],
    "fraud_raw.device_events": [
        ("event_id", "VARCHAR"),
        ("account_id", "VARCHAR"),
        ("device_fingerprint", "VARCHAR"),
        ("ip_address", "VARCHAR"),
        ("seen_at", "TIMESTAMP"),
    ],
    "fraud_curated.transactions_scored": [
        ("tx_id", "VARCHAR"),
        ("account_id", "VARCHAR"),
        ("fraud_score", "DOUBLE"),
        ("model_version", "VARCHAR"),
        ("scored_at", "TIMESTAMP"),
    ],
    "fraud_curated.scores_checked": [
        ("tx_id", "VARCHAR"),
        ("fraud_score", "DOUBLE"),
        ("expectation_suite", "VARCHAR"),
        ("passed", "BOOLEAN"),
    ],
    "crm_raw.contacts": [
        ("contact_id", "VARCHAR"),
        ("email", "VARCHAR"),
        ("full_name", "VARCHAR"),
        ("postal_code", "VARCHAR"),
        ("created_at", "TIMESTAMP"),
    ],
    "crm_raw.accounts": [
        ("account_id", "VARCHAR"),
        ("contact_id", "VARCHAR"),
        ("opened_at", "TIMESTAMP"),
        ("segment", "VARCHAR"),
    ],
    "crm_raw.consent_events": [
        ("event_id", "VARCHAR"),
        ("contact_id", "VARCHAR"),
        ("channel", "VARCHAR"),
        ("granted", "BOOLEAN"),
        ("recorded_at", "TIMESTAMP"),
    ],
    "crm_curated.customers": [
        ("account_id", "VARCHAR"),
        ("email", "VARCHAR"),
        ("full_name", "VARCHAR"),
        ("segment", "VARCHAR"),
    ],
    "crm_curated.consent_state": [
        ("contact_id", "VARCHAR"),
        ("channel", "VARCHAR"),
        ("granted", "BOOLEAN"),
        ("valid_from", "TIMESTAMP"),
    ],
    "billing_raw.orders": [
        ("order_id", "VARCHAR"),
        ("account_id", "VARCHAR"),
        ("amount_eur", "DOUBLE"),
        ("placed_at", "TIMESTAMP"),
    ],
    "billing_curated.invoices": [
        ("invoice_id", "VARCHAR"),
        ("account_id", "VARCHAR"),
        ("amount_eur", "DOUBLE"),
        ("due_on", "DATE"),
    ],
    "billing_curated.dunning_cases": [
        ("case_id", "VARCHAR"),
        ("invoice_id", "VARCHAR"),
        ("account_id", "VARCHAR"),
        ("stage", "VARCHAR"),
        ("opened_on", "DATE"),
    ],
}


@dataclass(frozen=True)
class Pipeline:
    """One scheduled job, and what it would declare if it declared anything."""

    domain: str
    name: str
    emitter: str
    hour: int
    minute: int
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    purpose: str
    legal_basis: str
    job_type: str = "BATCH"
    #: Weekly jobs run on Mondays. The mixed cadence is what makes the `runs`
    #: column in the record read as a schedule.
    weekly: bool = False
    #: Days (0-based, from START) this run fails. A fortnight of production
    #: lineage with nothing failing in it is not production lineage.
    fails_on: tuple[int, ...] = ()
    sql: str = ""

    @property
    def namespace(self) -> str:
        return f"acme.{self.domain}"

    @property
    def key(self) -> str:
        return f"{self.namespace}/{self.name}"

    def runs_on(self, day: int) -> bool:
        return (START + timedelta(days=day)).weekday() == 0 if self.weekly else True


PIPELINES = (
    Pipeline(
        domain="fraud",
        name="transactions-scored-daily",
        emitter="dbt",
        hour=2,
        minute=15,
        inputs=("fraud_raw.transactions", "fraud_raw.device_events"),
        outputs=("fraud_curated.transactions_scored",),
        purpose="fraud-detection",
        legal_basis="legitimate-interest",
        sql=(
            "select t.tx_id, t.account_id, score(t.*, d.*) as fraud_score "
            "from fraud_raw.transactions t "
            "left join fraud_raw.device_events d using (account_id)"
        ),
    ),
    Pipeline(
        domain="fraud",
        name="scores-validated",
        emitter="airflow",
        hour=2,
        minute=45,
        inputs=("fraud_curated.transactions_scored",),
        outputs=("fraud_curated.scores_checked",),
        purpose="data-quality-validation",
        legal_basis="legitimate-interest",
        fails_on=(3,),
    ),
    Pipeline(
        domain="crm",
        name="customers-curated",
        emitter="dbt",
        hour=1,
        minute=30,
        inputs=("crm_raw.contacts", "crm_raw.accounts"),
        outputs=("crm_curated.customers",),
        purpose="customer-administration",
        legal_basis="contract",
        sql=(
            "select a.account_id, c.email, c.full_name, a.segment "
            "from crm_raw.accounts a join crm_raw.contacts c using (contact_id)"
        ),
    ),
    # The job the mapping file misses. Added to the platform after somebody
    # wrote `qedro.yaml` and never added to it — which is how a register kept
    # by hand rots, and the reason the demo has one.
    Pipeline(
        domain="crm",
        name="consent-sync",
        emitter="spark",
        hour=3,
        minute=5,
        inputs=("crm_raw.consent_events",),
        outputs=("crm_curated.consent_state",),
        purpose="consent-management",
        legal_basis="legal-obligation",
        job_type="STREAMING",
    ),
    Pipeline(
        domain="billing",
        name="invoices-nightly",
        emitter="airflow",
        hour=4,
        minute=0,
        inputs=("billing_raw.orders", "crm_curated.customers"),
        outputs=("billing_curated.invoices",),
        purpose="invoicing",
        legal_basis="contract",
    ),
    Pipeline(
        domain="billing",
        name="dunning-weekly",
        emitter="dbt",
        hour=5,
        minute=20,
        inputs=("billing_curated.invoices",),
        outputs=("billing_curated.dunning_cases",),
        purpose="debt-collection",
        legal_basis="legitimate-interest",
        weekly=True,
        fails_on=(7,),
        sql=(
            "select invoice_id, account_id, dunning_stage(due_on) as stage "
            "from billing_curated.invoices where due_on < current_date"
        ),
    ),
)

#: Namespace for the deterministic run IDs. Any fixed UUID would do; this one
#: is derived from the demo's own name so it is reproducible from the source.
RUN_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://cordata.tech/qedro/demo")


@dataclass
class Estate:
    """The events, grouped by the file each one is written to."""

    declared: bool
    files: dict[str, list[dict]] = field(default_factory=dict)

    def add(self, emitter: str, event: dict) -> None:
        self.files.setdefault(emitter, []).append(event)


def _facet(payload: dict, producer: str, schema: str) -> dict:
    """A facet with the envelope OpenLineage requires on every one."""
    return {"_producer": producer, "_schemaURL": schema, **payload}


def _dataset(name: str, producer: str) -> dict:
    facets = {
        "dataSource": _facet(
            {
                "name": "warehouse",
                "uri": "jdbc:postgresql://warehouse.acme.internal:5432/analytics",
            },
            producer,
            f"{FACET_SPEC}/DatasourceDatasetFacet.json#/$defs/DatasourceDatasetFacet",
        )
    }
    if name in SCHEMAS:
        facets["schema"] = _facet(
            {"fields": [{"name": f, "type": t} for f, t in SCHEMAS[name]]},
            producer,
            f"{FACET_SPEC}/SchemaDatasetFacet.json#/$defs/SchemaDatasetFacet",
        )
    return {"namespace": "warehouse", "name": name, "facets": facets}


def _job(pipeline: Pipeline, producer: str, *, declared: bool) -> dict:
    facets = {
        "jobType": _facet(
            {
                "processingType": pipeline.job_type,
                "integration": pipeline.emitter.upper(),
                "jobType": "MODEL" if pipeline.emitter == "dbt" else "JOB",
            },
            producer,
            f"{FACET_SPEC}/JobTypeJobFacet.json#/$defs/JobTypeJobFacet",
        )
    }
    if pipeline.sql:
        facets["sql"] = _facet(
            {"query": pipeline.sql},
            producer,
            f"{FACET_SPEC}/SQLJobFacet.json#/$defs/SQLJobFacet",
        )
    if declared:
        # The whole difference between the two estates.
        facets["processing"] = _facet(
            {"purpose": pipeline.purpose, "legal_basis": pipeline.legal_basis},
            producer,
            PROCESSING_SCHEMA,
        )
    return {"namespace": pipeline.namespace, "name": pipeline.name, "facets": facets}


def _run(pipeline: Pipeline, day: int, started: datetime, producer: str) -> dict:
    run_id = str(uuid.uuid5(RUN_NAMESPACE, f"{pipeline.key}/{day}"))
    nominal = started.replace(hour=0, minute=0)
    return {
        "runId": run_id,
        "facets": {
            "nominalTime": _facet(
                {
                    "nominalStartTime": nominal.isoformat(),
                    "nominalEndTime": (nominal + timedelta(days=1)).isoformat(),
                },
                producer,
                f"{FACET_SPEC}/NominalTimeRunFacet.json#/$defs/NominalTimeRunFacet",
            )
        },
    }


def _events(pipeline: Pipeline, day: int, *, declared: bool) -> list[dict]:
    producer = EMITTERS[pipeline.emitter]
    started = START + timedelta(days=day, hours=pipeline.hour, minutes=pipeline.minute)
    finished = started + timedelta(minutes=6 + (day % 4))
    failed = day in pipeline.fails_on

    run = _run(pipeline, day, started, producer)
    job = _job(pipeline, producer, declared=declared)

    def envelope(event_type: str, when: datetime) -> dict:
        return {
            "eventTime": when.isoformat(),
            "eventType": event_type,
            "producer": producer,
            "schemaURL": SPEC,
            "run": dict(run),
            "job": job,
        }

    # START carries no datasets: several real integrations emit it before the
    # plan is resolved, and a reader that needed them there would be wrong
    # about half the estates it meets.
    events = [envelope("START", started)]

    if failed:
        terminal = envelope("FAIL", finished)
        terminal["run"] = {
            **run,
            "facets": {
                **run["facets"],
                "errorMessage": _facet(
                    {
                        "message": "upstream partition missing",
                        "programmingLanguage": "PYTHON",
                    },
                    producer,
                    f"{FACET_SPEC}/ErrorMessageRunFacet.json#/$defs/ErrorMessageRunFacet",
                ),
            },
        }
        events.append(terminal)
        return events

    complete = envelope("COMPLETE", finished)
    complete["inputs"] = [_dataset(name, producer) for name in pipeline.inputs]
    complete["outputs"] = [_dataset(name, producer) for name in pipeline.outputs]
    events.append(complete)
    return events


def build(*, declared: bool) -> Estate:
    estate = Estate(declared=declared)
    for day in range(DAYS):
        for pipeline in PIPELINES:
            if not pipeline.runs_on(day):
                continue
            for event in _events(pipeline, day, declared=declared):
                estate.add(pipeline.emitter, event)
    return estate


def render(estate: Estate) -> dict[str, str]:
    """Estate to filename → newline-delimited JSON.

    Sorted by event time within a file, because that is the order an emitter
    would have written them in and a reader comparing two estates should see
    the same lines in the same places.
    """
    out = {}
    for emitter, events in sorted(estate.files.items()):
        ordered = sorted(events, key=lambda e: (e["eventTime"], e["job"]["name"], e["eventType"]))
        body = "\n".join(json.dumps(e, sort_keys=True, ensure_ascii=False) for e in ordered)
        out[f"{emitter}.ndjson"] = body + "\n"
    return out


def estates() -> dict[str, dict[str, str]]:
    return {
        "lineage": render(build(declared=False)),
        "lineage-declared": render(build(declared=True)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; fail if what is committed differs from what this would produce",
    )
    args = parser.parse_args(argv)

    stale = []
    for directory, files in estates().items():
        target = DEMO / directory
        for name, body in files.items():
            path = target / name
            if args.check:
                if not path.exists() or path.read_text(encoding="utf-8") != body:
                    stale.append(path.relative_to(ROOT))
                continue
            target.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

    if args.check:
        if stale:
            print("out of date, run `python tools/seed.py`:", file=sys.stderr)
            for path in stale:
                print(f"  {path}", file=sys.stderr)
            return 1
        print("demo/ is current")
        return 0

    total = sum(len(body.splitlines()) for files in estates().values() for body in files.values())
    print(f"wrote {total:,} events across {len(estates())} estates in {DEMO.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
