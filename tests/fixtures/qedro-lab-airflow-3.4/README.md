Real OpenLineage from [qedro-lab](https://github.com/cordata-tech/qedro-lab), not
hand-written.

`events.jsonl` is 56 events from two days of a fictitious company's Airflow DAG run
under Airflow's scheduler, captured on 2026-11-21 at qedro-lab commit `1ab66fb` with
`lab capture airflow-3.4-parents --days 2`, after `scheduled.sh 1` and
`scheduled.sh 2` on a fresh stack. The same events reached Marquez, Kafka and three
bucket emulators through one composite transport, and `lab check` found every source
identical. Nothing was removed.

Four emitters in one run:

- **Airflow 3.4.0 with its OpenLineage provider 2.21.0**: the DAG run `acme/acme_daily`
  and its tasks, one with lineage declared as Assets (`load_raw`), one with lineage the
  provider parsed from SQL (`daily_revenue`), and two that only launch other emitters.
- **dbt-ol over dbt-postgres**, run from the `dbt_run` task with
  `OPENLINEAGE_PARENT_ID`, so its invocation `acme/dbt-run-acme` names the task as its
  parent and each model names the invocation.
- **art30-emit 0.2.0**, which emits the `processing` facet for
  `acme.crm/newsletter-export` and names the launching task as its parent.
- **pipeline-runtime 0.2.13**, three pipelines with the `processing` facet and a
  `.validate` child each, naming the launching task as their parent.

What it is here for (cordata-tech/qedro#8): an orchestration hierarchy three levels deep
— DAG run, task, dbt invocation — where qedro must leave every level out of the
activities. Each of the three tasks that launches an emitter is named as parent through
`OPENLINEAGE_PARENT_ID`, by dbt-ol, art30-emit 0.2.0 (art30-emit#1) and
pipeline-runtime 0.2.13 (pipeline-runtime#19), so the record has 12 activities and
every one has a purpose. With art30-emit 0.1.0 and pipeline-runtime 0.2.12, which named
no parent, two of the launching tasks showed as activities with nothing declared.

Under `airflow dags test` the same DAG emits no `START` for the DAG run and files one
task's hook-level SQL lineage under the next task, so qedro-lab captures under the
scheduler; its README has the detail.

## Versions

- `adlfs==2026.8.0`
- `apache-airflow-providers-common-sql==3.0.0`
- `apache-airflow-providers-openlineage==2.21.0`
- `apache-airflow-providers-postgres==7.1.2`
- `apache/airflow:3.4.0-python3.12`
- `apache/kafka:4.4.0`
- `art30-emit==0.2.0`
- `confluent-kafka==2.16.2`
- `cordata-pipeline-runtime[run]==0.2.13`
- `dbt-core==1.12.7`
- `dbt-postgres==1.11.0`
- `fsouza/fake-gcs-server:1.56.1`
- `gcsfs==2026.10.1`
- `marquezproject/marquez-web:0.51.1`
- `marquezproject/marquez:0.51.1`
- `mcr.microsoft.com/azure-storage/azurite:3.38.0`
- `motoserver/moto:5.2.5`
- `openlineage-dbt==1.55.0`
- `openlineage-python[kafka,fsspec]==1.55.0`
- `postgres:16.16`
- `psycopg[binary]==3.3.9`
- `qedro[s3,gcs,azure]==0.25.0`
- `s3fs==2026.9.0`
