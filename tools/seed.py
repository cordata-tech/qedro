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
import hashlib
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

#: Three weeks, chosen by the weekly job rather than by the daily ones. A
#: fortnight gives `dunning-weekly` two runs, one of which fails, which leaves
#: a single assertion in the quality history — enough to be correct and not
#: enough to look like a schedule. Three weeks gives it three.
#:
#: Starts on Monday 6 July 2026. It started on Monday 1 June until the deployer
#: view was reviewed for platform#48: `pipeline-runtime` emits the model version
#: `2026-07-fraud-v3`, and a June window could only have carried that name as a
#: model from the future. Five weeks later is still a Monday, so every weekly run,
#: every failure day and every count is unchanged — only the dates moved.
START = datetime(2026, 7, 6, tzinfo=UTC)
DAYS = 21

#: Real OpenLineage producer strings. The integrations are named because the
#: whole claim is that this works against what people already run — an estate
#: whose events all came from one emitter would not demonstrate that.
EMITTERS = {
    "dbt": "https://github.com/OpenLineage/OpenLineage/tree/1.24.2/integration/dbt",
    "airflow": "https://github.com/OpenLineage/OpenLineage/tree/1.24.2/integration/airflow",
    "spark": "https://github.com/OpenLineage/OpenLineage/tree/1.24.2/integration/spark",
}

SPEC = "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent"

#: The one repository the platform lives in. Commits are derived from the job
#: and the day, so they are stable and look like commits without being any.
REPO = "https://github.com/acme-finanz/data-platform"
BRANCH = "main"
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
#: What each dataset holds, as the standard `tags` dataset facet carries it:
#: `(key, value)`, or `(key, value, column)` where the tag is about one field.
#: This is where an Art. 30 record's categories, data subjects, residency and
#: retention come from — see cordata-tech/qedro#13.
#:
#: **Both estates carry it.** Classification is declared by whoever owns the
#: dataset and travels with the data; whether the *pipeline* declares its
#: purpose is a separate decision, and that difference is the one the two
#: estates exist to show.
#:
#: Two datasets are deliberately absent. `fraud_raw.device_events` is a vendor
#: feed nobody classified and `crm_raw.accounts` was never got round to, which
#: is what an estate looks like — and the record says *nobody said* rather than
#: *no personal data*.
CLASSIFICATION: dict[str, tuple[tuple[str, ...], ...]] = {
    "fraud_raw.transactions": (
        ("data_category", "financial"),
        ("data_category", "identification", "iban"),
        ("subject_type", "customer"),
        ("residency", "eu"),
        ("retention", "7y"),
    ),
    "fraud_curated.transactions_scored": (
        ("data_category", "financial"),
        ("data_category", "behavioural"),
        ("subject_type", "customer"),
        ("residency", "eu"),
        ("retention", "7y"),
    ),
    "fraud_curated.scores_checked": (
        ("data_category", "behavioural"),
        ("subject_type", "customer"),
        ("residency", "eu"),
        ("retention", "1y"),
    ),
    "crm_raw.contacts": (
        ("data_category", "identification"),
        ("data_category", "contact", "email"),
        ("subject_type", "prospect"),
        ("residency", "eu"),
        ("retention", "7y"),
    ),
    "crm_raw.consent_events": (
        ("data_category", "identification"),
        ("subject_type", "customer"),
        ("residency", "eu"),
        ("retention", "7y"),
    ),
    "crm_curated.customers": (
        ("data_category", "identification"),
        ("data_category", "contact", "email"),
        ("subject_type", "customer"),
        ("residency", "eu"),
        ("retention", "7y"),
    ),
    "crm_curated.consent_state": (
        ("data_category", "identification"),
        ("subject_type", "customer"),
        ("residency", "eu"),
        ("retention", "7y"),
    ),
    "billing_raw.orders": (
        ("data_category", "financial"),
        ("subject_type", "customer"),
        ("residency", "eu"),
        ("retention", "10y"),
    ),
    "billing_curated.invoices": (
        ("data_category", "financial"),
        ("subject_type", "customer"),
        # Ten years, which is what commercial and tax retention duties commonly
        # require in DACH jurisdictions — a period somebody declared, never a
        # measurement of how long the table was in fact kept.
        ("residency", "eu"),
        ("retention", "10y"),
    ),
    "billing_curated.dunning_cases": (
        ("data_category", "financial"),
        ("data_category", "behavioural"),
        ("subject_type", "customer"),
        ("residency", "eu"),
        ("retention", "10y"),
    ),
}

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
class Expectation:
    """One data-quality assertion a job makes about a dataset it reads.

    `fails_on` is the list of days it does not hold. A fortnight of assertions
    that all pass demonstrates the happy path and nothing else — the whole
    reason to look at an assertion history is the day one stopped holding.
    """

    assertion: str
    column: str = ""
    fails_on: tuple[int, ...] = ()


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
    #: Days this job runs on, when it is not scheduled at all. An erasure
    #: happens once, in response to a request, and a demo where it recurred
    #: nightly would be describing something else.
    only_on: tuple[int, ...] = ()
    #: The output this job erases, and how. Emitted as the standard
    #: `lifecycleStateChange` dataset facet, which is what lets `qedro erasure`
    #: read the instant as evidence rather than take it from `--since`.
    erases: str = ""
    lifecycle: str = "OVERWRITE"
    sql: str = ""
    #: Path in the platform repository. The `sourceCodeLocation` job facet is
    #: standard OpenLineage and dbt, Airflow and Spark all emit it — which is
    #: what lets the provenance chain name a commit without anything of ours.
    code_path: str = ""
    #: Data-quality assertions this job makes, and the dataset they are about.
    #: Emitted as the standard `dataQualityAssertions` **input** facet, which is
    #: where Great Expectations and dbt put them: the claim is about one run's
    #: use of the dataset, not about the dataset.
    asserts_on: str = ""
    asserts: tuple[Expectation, ...] = ()
    #: The model a job runs, as `(first day, version)` pairs. Emitted as a
    #: `model_version` entry in the standard OpenLineage `tags` run facet, which
    #: any client can add — nothing here is specific to Cordata. The version
    #: changes part-way through the window because the deployer view exists to
    #: say which model ran on which run, and a single version never tests that.
    models: tuple[tuple[int, str], ...] = ()

    @property
    def namespace(self) -> str:
        return f"acme.{self.domain}"

    @property
    def key(self) -> str:
        return f"{self.namespace}/{self.name}"

    def model_version(self, day: int) -> str:
        current = ""
        for first_day, version in self.models:
            if day >= first_day:
                current = version
        return current

    def runs_on(self, day: int) -> bool:
        if self.only_on:
            return day in self.only_on
        return (START + timedelta(days=day)).weekday() == 0 if self.weekly else True


PIPELINES = (
    Pipeline(
        domain="fraud",
        name="transactions-scored-daily",
        code_path="models/fraud/transactions_scored.sql",
        emitter="dbt",
        hour=2,
        minute=15,
        inputs=("fraud_raw.transactions", "fraud_raw.device_events"),
        outputs=("fraud_curated.transactions_scored",),
        purpose="fraud-detection",
        legal_basis="legitimate-interest",
        models=((0, "2026-06-fraud-v2"), (14, "2026-07-fraud-v3")),
        sql=(
            "select t.tx_id, t.account_id, score(t.*, d.*) as fraud_score "
            "from fraud_raw.transactions t "
            "left join fraud_raw.device_events d using (account_id)"
        ),
    ),
    Pipeline(
        domain="fraud",
        name="scores-validated",
        code_path="dags/fraud/scores_validated.py",
        emitter="airflow",
        hour=2,
        minute=45,
        inputs=("fraud_curated.transactions_scored",),
        outputs=("fraud_curated.scores_checked",),
        purpose="data-quality-validation",
        legal_basis="legitimate-interest",
        fails_on=(3,),
        asserts_on="fraud_curated.transactions_scored",
        asserts=(
            Expectation("expect_column_values_to_not_be_null", "tx_id"),
            Expectation("expect_column_values_to_be_unique", "tx_id"),
            Expectation("expect_column_values_to_be_between", "fraud_score"),
            Expectation("expect_column_values_to_not_be_null", "account_id"),
            # The interesting one. Scoring volume drops on two days and the
            # row-count expectation catches it.
            Expectation("expect_table_row_count_to_be_between", fails_on=(5, 9)),
        ),
    ),
    Pipeline(
        domain="crm",
        name="customers-curated",
        code_path="models/crm/customers.sql",
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
        code_path="jobs/crm/consent_sync.scala",
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
        code_path="dags/billing/invoices_nightly.py",
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
        code_path="models/billing/dunning_cases.sql",
        emitter="dbt",
        hour=5,
        minute=20,
        inputs=("billing_curated.invoices",),
        outputs=("billing_curated.dunning_cases",),
        purpose="debt-collection",
        legal_basis="legitimate-interest",
        weekly=True,
        fails_on=(7,),
        asserts_on="billing_curated.invoices",
        asserts=(
            Expectation("expect_column_values_to_not_be_null", "invoice_id"),
            Expectation("expect_column_values_to_be_unique", "invoice_id"),
            Expectation("expect_column_values_to_be_between", "amount_eur"),
        ),
        sql=(
            "select invoice_id, account_id, dunning_stage(due_on) as stage "
            "from billing_curated.invoices where due_on < current_date"
        ),
    ),
    Pipeline(
        domain="crm",
        name="subject-erasure",
        code_path="dags/crm/subject_erasure.py",
        emitter="airflow",
        hour=9,
        minute=12,
        # Reads nothing and rewrites the table in place, which is what an
        # erasure job does: the rows for one data subject are deleted and the
        # table is written back. It is itself processing, and belongs in the
        # Art. 30 record like any other job.
        inputs=(),
        outputs=("crm_raw.contacts",),
        erases="crm_raw.contacts",
        purpose="subject-rights-handling",
        legal_basis="legal-obligation",
        # Once, on the 22nd. Late enough that the weekly dunning job does not
        # run again inside the window — so the demo shows an erasure that
        # propagated to two descendants out of three, and names the third.
        # An estate where everything was rewritten in time is not one anybody
        # has, and the hole is the output this projection exists for.
        only_on=(16,),
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


def _assertions(pipeline: Pipeline, day: int, producer: str) -> dict:
    return _facet(
        {
            "assertions": [
                {
                    "assertion": e.assertion,
                    **({"column": e.column} if e.column else {}),
                    "success": day not in e.fails_on,
                }
                for e in pipeline.asserts
            ]
        },
        producer,
        f"{FACET_SPEC}/DataQualityAssertionsDatasetFacet.json"
        "#/$defs/DataQualityAssertionsDatasetFacet",
    )


def _dataset(
    name: str,
    producer: str,
    assertions: dict | None = None,
    *,
    lifecycle: str = "",
) -> dict:
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
    if name in CLASSIFICATION:
        # The standard `tags` dataset facet, spec 1-0-0. `source` says what put
        # the tag there, as `pipeline-runtime` does with the LF-tags it resolves
        # (cordata-tech/pipeline-runtime#3); `field` names a column when the tag
        # is about one rather than about the whole dataset.
        facets["tags"] = _facet(
            {
                "tags": [
                    {"key": tag[0], "value": tag[1], "source": "CATALOG"}
                    | ({"field": tag[2]} if len(tag) > 2 else {})
                    for tag in CLASSIFICATION[name]
                ]
            },
            producer,
            "https://openlineage.io/spec/facets/1-0-0/TagsDatasetFacet.json"
            "#/$defs/TagsDatasetFacet",
        )
    if lifecycle:
        # A dataset facet rather than an output facet: *this table was
        # overwritten* is true of the table, not only of one run's use of it.
        facets["lifecycleStateChange"] = _facet(
            {"lifecycleStateChange": lifecycle},
            producer,
            "https://openlineage.io/spec/facets/1-0-1/LifecycleStateChangeDatasetFacet.json"
            "#/$defs/LifecycleStateChangeDatasetFacet",
        )
    out: dict = {"namespace": "warehouse", "name": name, "facets": facets}
    if assertions is not None:
        # An *input* facet, not a dataset facet. The distinction is the whole
        # reason the assertion history can speak in dates.
        out["inputFacets"] = {"dataQualityAssertions": assertions}
    return out


def _commit(pipeline: Pipeline, day: int) -> str:
    """A stable fake commit SHA.

    Changes when the code changes rather than every day — a pipeline whose
    commit moved nightly would make the provenance chain look like churn, and
    real ones do not.
    """
    seed = f"{pipeline.key}@{day // 7}"
    return hashlib.sha1(seed.encode()).hexdigest()


def _job(pipeline: Pipeline, producer: str, day: int, *, declared: bool) -> dict:
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
    if pipeline.code_path:
        facets["sourceCodeLocation"] = _facet(
            {
                "type": "git",
                "repoUrl": REPO,
                "url": f"{REPO}/blob/{BRANCH}/{pipeline.code_path}",
                "path": pipeline.code_path,
                "version": _commit(pipeline, day),
                "branch": BRANCH,
            },
            producer,
            f"{FACET_SPEC}/SourceCodeLocationJobFacet.json#/$defs/SourceCodeLocationJobFacet",
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
    facets = {
        "nominalTime": _facet(
            {
                "nominalStartTime": nominal.isoformat(),
                "nominalEndTime": (nominal + timedelta(days=1)).isoformat(),
            },
            producer,
            f"{FACET_SPEC}/NominalTimeRunFacet.json#/$defs/NominalTimeRunFacet",
        )
    }
    version = pipeline.model_version(day)
    if version:
        # The standard TagsRunFacet, spec 1-0-0: `key` and `value` required,
        # `source` optional. Emitted on every event of the run, as the
        # OpenLineage client does with its own tags.
        facets["tags"] = _facet(
            {"tags": [{"key": "model_version", "value": version, "source": "USER"}]},
            producer,
            "https://openlineage.io/spec/facets/1-0-0/TagsRunFacet.json#/$defs/TagsRunFacet",
        )
    return {"runId": run_id, "facets": facets}


def _events(pipeline: Pipeline, day: int, *, declared: bool) -> list[dict]:
    producer = EMITTERS[pipeline.emitter]
    started = START + timedelta(days=day, hours=pipeline.hour, minutes=pipeline.minute)
    finished = started + timedelta(minutes=6 + (day % 4))
    failed = day in pipeline.fails_on

    run = _run(pipeline, day, started, producer)
    job = _job(pipeline, producer, day, declared=declared)

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

    asserted = _assertions(pipeline, day, producer) if pipeline.asserts else None
    complete = envelope("COMPLETE", finished)
    complete["inputs"] = [
        _dataset(name, producer, asserted if name == pipeline.asserts_on else None)
        for name in pipeline.inputs
    ]
    complete["outputs"] = [
        _dataset(
            name,
            producer,
            lifecycle=pipeline.lifecycle if name == pipeline.erases else "",
        )
        for name in pipeline.outputs
    ]
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
