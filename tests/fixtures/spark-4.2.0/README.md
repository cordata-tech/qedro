Real OpenLineage from Spark, not hand-written.

`events.jsonl` is one local run of a two-action PySpark application, captured on
2026-09-17 with Spark 4.2.0 on Java 21 and `openlineage-spark_2.13` 1.53.0,
inside an image built from `python:3.12-slim-trixie`
(`sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`).
The job, Dockerfile and command are in `cordata/spark-lineage-probe`. Nothing was
removed: the only machine-specific values are the container's hostname and
`root` as the user.

Twenty-five events. The application run, `default/orders_enrichment`, is the
parent of every other run through the standard `ParentRunFacet`. Two child jobs
are the actions the code asked for:

- `…adaptive_spark_plan.out_orders_enriched` joins two CSV files and writes Parquet;
- `…adaptive_spark_plan.out_revenue_by_region` aggregates that and writes Parquet.

Three more child jobs are actions Spark ran on its own to read the CSV headers
and the Parquet schema: `collect_limit` and `deserialize_to_object` (two runs
each) and `map_partitions_parallel_collection`. They report inputs and no
outputs, so Qedro lists them as activities, which turns an application that wrote
two datasets into five activities. Since #22 the scope statement names all three on a
`read only` line; they are not dropped, because the events cannot tell them from a real
job that only reads.

What it is here for (cordata-tech/qedro#10): #8's parent rule against a third
emitter, where the application run must be left out of the activities. The
namespace was left unset, so every job carries the listener's default, `default`.
Files arrive as namespace `file` with an absolute path, as with Airflow; Qedro prints
them as `file:///probe/...` since #23.
