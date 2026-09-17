Real OpenLineage from dbt, not hand-written.

`events.jsonl` is copied from `cordata/dbt-column-lineage-probe/events.sample.jsonl`,
a captured `dbt-ol run` with dbt-core 1.12.4, dbt-duckdb 1.11.0 and
openlineage-dbt 1.53.0, verified on 2026-09-08. Ten events: one invocation job,
`dbt/dbt-run-dbtprobe`, and four model jobs whose runs name the invocation's run
in the standard `ParentRunFacet` (spec 1-2-0).

It is here for cordata-tech/qedro#8, and for the same reason as
`../events/pipeline-runtime.ndjson`: an emitter nobody on this project wrote
disagrees with the parser in ways a hand-written fixture cannot. Running the
projections against it first found four bugs on 2026-09-17.
