"""Write `docs/examples/erasure/lineage.ndjson`, the lineage behind the README's tree.

The demo's erasures are straight chains of at most three datasets, and the
demo cannot grow a branch without changing `docs/evidence/erasure.md`, which a
published post cites. So the README's picture of an erasure comes from this
small, separate estate instead, built so that one tree shows every state a
descendant can be in:

- `crm_curated.customers` and `ml_features.churn_inputs` are dbt models
  materialised as a table and a view, rebuilt after the erasure;
- `marketing.audiences` is an incremental model, only appended to since;
- `billing_curated.invoices` and `exports.partner_feed` were written after it
  by jobs that do not say how;
- `billing_curated.dunning_cases` comes from a weekly job that last ran before.

Anyone can run the README's command against it:

    qedro erasure docs/examples/erasure --dataset crm_raw.contacts

    python tools/erasure_example.py           # rewrite the file
    python tools/erasure_example.py --check   # fail if it is out of date
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from qedro.demo import EMITTERS, FACET_SPEC, SPEC

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "docs" / "examples" / "erasure" / "lineage.ndjson"
RUNS = uuid.uuid5(uuid.NAMESPACE_URL, "https://cordata.tech/qedro/examples/erasure")
LIFECYCLE = (
    "https://openlineage.io/spec/facets/1-0-1/LifecycleStateChangeDatasetFacet.json"
    "#/$defs/LifecycleStateChangeDatasetFacet"
)

#: (job namespace, job name, emitter, reads, writes, when, how it wrote)
#: `how` is a lifecycle state for the erasure, a dbt materialisation for a
#: model, or "" for a job that does not say.
RUNS_IN_ORDER = (
    ("acme.billing", "dunning-weekly", "airflow",
     ["billing_curated.invoices"], ["billing_curated.dunning_cases"], (20, 5, 28), ""),
    ("acme.crm", "subject-erasure", "airflow",
     [], ["crm_raw.contacts"], (22, 9, 18), "OVERWRITE"),
    ("acme.crm", "customers-curated", "dbt",
     ["crm_raw.contacts"], ["crm_curated.customers"], (23, 1, 36), "table"),
    ("acme.marketing", "audiences", "dbt",
     ["crm_raw.contacts"], ["marketing.audiences"], (23, 2, 10), "incremental"),
    ("acme.billing", "invoices-nightly", "airflow",
     ["crm_curated.customers"], ["billing_curated.invoices"], (23, 4, 6), ""),
    ("acme.ml", "churn-features", "dbt",
     ["crm_curated.customers"], ["ml_features.churn_inputs"], (23, 4, 40), "view"),
    ("acme.marketing", "partner-export", "spark",
     ["marketing.audiences"], ["exports.partner_feed"], (23, 6, 0), ""),
)  # fmt: skip


def _facet(payload: dict, producer: str, schema: str) -> dict:
    return {"_producer": producer, "_schemaURL": schema, **payload}


def _dataset(name: str, producer: str, how: str = "") -> dict:
    out: dict = {"namespace": "warehouse", "name": name}
    if how.isupper():
        out["facets"] = {
            "lifecycleStateChange": _facet({"lifecycleStateChange": how}, producer, LIFECYCLE)
        }
    elif how:
        # As openlineage-dbt sends it on each output.
        out["facets"] = {"dbt_model": {"config": {"materialized": how}}}
    return out


def events() -> list[dict]:
    out = []
    for namespace, name, emitter, reads, writes, (day, hour, minute), how in RUNS_IN_ORDER:
        producer = EMITTERS[emitter]
        started = datetime(2026, 7, day, hour, minute, tzinfo=UTC)
        run = {"runId": str(uuid.uuid5(RUNS, f"{namespace}/{name}/{day}"))}
        job = {
            "namespace": namespace,
            "name": name,
            "facets": {
                "jobType": _facet(
                    {
                        "processingType": "BATCH",
                        "integration": emitter.upper(),
                        "jobType": "MODEL" if emitter == "dbt" else "JOB",
                    },
                    producer,
                    f"{FACET_SPEC}/JobTypeJobFacet.json#/$defs/JobTypeJobFacet",
                )
            },
        }
        envelope = {"producer": producer, "schemaURL": SPEC, "run": run, "job": job}
        out.append({"eventTime": started.isoformat(), "eventType": "START", **envelope})
        out.append(
            {
                "eventTime": (started + timedelta(minutes=6)).isoformat(),
                "eventType": "COMPLETE",
                **envelope,
                "inputs": [_dataset(r, producer) for r in reads],
                "outputs": [_dataset(w, producer, how) for w in writes],
            }
        )
    return out


def rendered() -> str:
    return "".join(json.dumps(e, sort_keys=True) + "\n" for e in events())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the README's example erasure lineage.")
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args(argv)
    if args.check:
        if not PATH.exists() or PATH.read_text(encoding="utf-8") != rendered():
            print(f"{PATH.relative_to(ROOT)} is out of date — run {__file__}", file=sys.stderr)
            return 1
        print(f"{PATH.relative_to(ROOT)} is current", file=sys.stderr)
        return 0
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(rendered(), encoding="utf-8")
    print(f"wrote {PATH.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
