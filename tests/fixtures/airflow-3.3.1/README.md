Real OpenLineage from Airflow, not hand-written.

`events.jsonl` is one `airflow dags test` run of a three-task DAG, captured on
2026-09-17 with Airflow 3.3.1 and `apache-airflow-providers-openlineage` 2.20.1
(openlineage-python 1.52.0), inside `apache/airflow:3.3.1-python3.12`. The DAG,
Dockerfile and command are in `cordata/airflow-lineage-probe`. Nothing was
removed: the only machine-specific values are the container's hostname.

Seven events:

- `default/orders_daily.extract_orders` and `.score_orders` declare datasets
  through inlets and outlets, forming a chain of two;
- `default/orders_daily.notify` reads and writes nothing, and is not a parent;
- `default/orders_daily`, the DAG run, emitted only as `COMPLETE` under
  `airflow dags test`, and named by each task's run in the standard
  `ParentRunFacet`.

What it is here for (cordata-tech/qedro#10): #8's parent rule against a second
emitter, where the DAG run must be left out of the activities and `notify` must
stay in, because having no datasets alone does not make a job a parent. The
namespace was left unset, so every job carries the provider's default,
`default`, which is #9's guessed-domain case again.

Two things the capture showed that the synthetic demo could not:

- The provider sends `sourceCode` (the bash command) and not
  `sourceCodeLocation`, so `provenance` reports no code location.
- File datasets arrive as namespace `file` with an absolute path as the name,
  which Qedro prints as `file//data/...` (#23).
