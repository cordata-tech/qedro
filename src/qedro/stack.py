"""Where a step ran and where its data lives, as the events say (#39).

Two readings, each from evidence an emitter already sends:

- **What ran the step**, from the standard `jobType` job facet's `integration`
  (`DBT`, `AIRFLOW`, `SPARK`, …), or failing that from the event's `producer`,
  which for every integration in the OpenLineage repository is a URL ending in
  `/integration/<name>`.
- **Where the data lives**, from the scheme of the dataset's namespace —
  OpenLineage's naming puts the platform there: `snowflake://…`, `s3://…`,
  `bigquery` — or failing that from the URI in the `dataSource` dataset facet.

Neither is guessed from a name. An event that says neither gives an empty
`Stack`, and a renderer prints nothing rather than a placeholder.

The labels are data: `LABELS` holds the defaults, keyed by integration name and
URI scheme in lower case, and `platforms:` in `qedro.yaml` adds to them or
replaces one. The two readings treat an unlabelled value differently:

- An **integration** nobody has labelled is printed as the event gave it. The
  `jobType` facet exists to name the integration, so an unfamiliar one is still
  a statement about what ran.
- A **namespace scheme** nobody has labelled is not printed. A namespace is an
  identity first, and many are logical names written as URIs —
  pipeline-runtime's `cordata://fraud` names a domain, not a platform — so an
  unknown scheme says nothing about where data lives until somebody maps it in
  `platforms:`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .events import Dataset, Event

#: What the record prints for an integration or a namespace scheme. Lower-case
#: keys; `platforms:` in `qedro.yaml` is merged over these.
LABELS: Mapping[str, str] = {
    # What runs a step, as the `jobType` facet or the producer URL names it.
    "airflow": "Airflow",
    "dagster": "Dagster",
    "dbt": "dbt",
    "flink": "Flink",
    "great_expectations": "Great Expectations",
    "spark": "Spark",
    # Where data lives, as a namespace or a data source URI names it.
    "abfss": "Azure Data Lake",
    "awsathena": "Athena",
    "azurecosmos": "Cosmos DB",
    "bigquery": "BigQuery",
    "cassandra": "Cassandra",
    "clickhouse": "ClickHouse",
    "db2": "Db2",
    "dbfs": "Databricks",
    "duckdb": "DuckDB",
    "file": "local files",
    "gs": "Cloud Storage",
    "hdfs": "HDFS",
    "hive": "Hive",
    "kafka": "Kafka",
    "kinesis": "Kinesis",
    "mongodb": "MongoDB",
    "mssql": "SQL Server",
    "mysql": "MySQL",
    "oracle": "Oracle",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "redshift": "Redshift",
    "s3": "S3",
    "s3a": "S3",
    "snowflake": "Snowflake",
    "sqlite": "SQLite",
    "sqlserver": "SQL Server",
    "teradata": "Teradata",
    "trino": "Trino",
    "wasbs": "Azure Blob Storage",
}

_PRODUCER = re.compile(r"/integration/([A-Za-z0-9_-]+)")
_SCHEME = re.compile(r"^(?:jdbc:)?([A-Za-z][A-Za-z0-9+.-]*)://")


@dataclass(frozen=True)
class Stack:
    """What ran a step and where its output lives, each "" where nothing said."""

    ran_on: str = ""
    stored_in: str = ""

    def describe(self) -> str:
        """`dbt · Snowflake`, one side alone, or "" when neither is known."""
        return " · ".join(part for part in (self.ran_on, self.stored_in) if part)

    def __bool__(self) -> bool:
        return bool(self.ran_on or self.stored_in)


def ran_on(event: Event, labels: Mapping[str, str] = LABELS) -> str:
    """What ran *event*'s job, or "" when the event does not say."""
    job_type = event.job.facets.get("jobType")
    integration = job_type.get("integration") if isinstance(job_type, Mapping) else None
    if not (isinstance(integration, str) and integration.strip()):
        found = _PRODUCER.search(event.producer or "")
        integration = found.group(1) if found else ""
    return _label(integration.strip(), labels)


def stored_in(dataset: Dataset, labels: Mapping[str, str] = LABELS) -> str:
    """The platform *dataset*'s namespace or data source names, or ""."""
    source = dataset.facets.get("dataSource")
    uri = source.get("uri") if isinstance(source, Mapping) else None
    candidates = (
        _scheme(dataset.namespace),
        # Two namespaces are a bare word with no `://` after it: BigQuery, and
        # `file` for a local filesystem.
        dataset.namespace.lower() if dataset.namespace.lower() in {"bigquery", "file"} else "",
        _scheme(uri) if isinstance(uri, str) else "",
    )
    return next((labels[c] for c in candidates if c in labels), "")


def of(events: Iterable[Event], dataset: str, labels: Mapping[str, str] = LABELS) -> Stack:
    """What ran the runs that wrote *dataset*, and where it lives.

    The first event that says each wins, in the order given. One that names
    neither costs nothing: an emitter may put its facets on START and not on
    COMPLETE, or the other way round.
    """
    ran, stored = "", ""
    for event in events:
        output = next((o for o in event.outputs if o.key == dataset), None)
        if output is None:
            continue
        ran = ran or ran_on(event, labels)
        stored = stored or stored_in(output, labels)
        if ran and stored:
            break
    return Stack(ran_on=ran, stored_in=stored)


def where(events: Iterable[Event], dataset: str, labels: Mapping[str, str] = LABELS) -> str:
    """Where *dataset* lives, from any event that names it, written or read."""
    for event in events:
        for side in (event.outputs, event.inputs):
            for d in side:
                if d.key == dataset and (found := stored_in(d, labels)):
                    return found
    return ""


def labels(extra: Mapping[str, str]) -> Mapping[str, str]:
    """The defaults with `platforms:` from `qedro.yaml` merged over them."""
    return {**LABELS, **{k.lower(): v for k, v in extra.items()}}


def _scheme(text: str) -> str:
    found = _SCHEME.match(text.strip())
    return found.group(1).lower() if found else ""


def _label(value: str, labels: Mapping[str, str]) -> str:
    if not value:
        return ""
    return labels.get(value.lower(), value)
