# What Qedro runs against

## The rule that makes this page worth keeping

**A row may only say `works` if a test names it and would fail if it broke.**

Everything in this project rests on the argument that a claim without evidence
is worth less than no claim. A compatibility matrix is nothing but claims, and
it is the easiest document in any repository to let rot — an integration listed
as supported that nobody has run in six months is the invisible hole this tool
exists to prevent, applied to its own documentation.

So each `works` row carries the test that proves it. A row with no test is
`candidate`, however finished the code feels.

| | Meaning |
|---|---|
| **works** | verified, and named by a test |
| **planned** | committed, with an issue |
| **candidate** | wanted, not committed, no date |
| **no** | deliberately not, and the reason is written down |

Tracked in [#5](https://github.com/cordata-tech/qedro/issues/5).

## Sources — where events are read from

| | State | Notes |
|---|---|---|
| Directory of `.json` / `.ndjson` / `.jsonl` | **works** | `tests/test_sources.py`, `tests/test_demo.py`. Nested directories are walked |
| Marquez-compatible HTTP API | **works** | `tests/test_cli.py::TestRopaAgainstAnApi` — the source-neutrality acceptance test |
| S3 / GCS / Azure Blob prefix | **candidate** | The real "cloud support" axis for a read-only tool: a bucket of exported events. One `read()` dispatch each, plus an optional dependency per cloud |
| Kafka topic | **candidate** | OpenLineage events frequently live on a topic and never on a disk |
| DataHub, OpenMetadata, Egeria | **candidate** | Each has its own API. Worth doing where somebody actually runs one |
| Accepting pushed events into a store of ours | **no** | It would make Qedro a second lineage warehouse competing with the backend you already run, and re-acquire the precondition that reading OpenLineage removed. Adapters run client-side instead |

## Documents read, other than events

Not every input is lineage. These are the documents a run can be handed, and each is
read for a different reason — which matters, because two of them are assertions and
the page would be misleading if it listed them beside evidence without saying so.

| | State | Notes |
|---|---|---|
| `qedro.yaml` — controller, domains, mapping rules | **works** | `tests/test_config.py`. YAML, JSON or TOML. The `jobs:` rules are a **fallback**, labelled as asserted wherever a value comes from them |
| A vocabulary document | **works** | `tests/test_vocabulary.py`. Replaces the shipped GDPR baseline wholesale rather than merging with it |
| A declared-activities document, `--activities` | **works** | `tests/test_ropa.py::TestDeclaredActivities` and `tests/test_deployer.py::TestDeclaredUseCases`. Processing that emits no lineage, **merged into the record** and marked declared; any declared entry withholds the mark (#6) |
| A register, as a side of `qedro diff` | **works** | `tests/test_register.py`. The declared-activities shape plus `job` and `owner`, **never merged into a record** — it is an outside claim being checked against one (#24) |
| A record this tool wrote, as a side of `qedro diff` | **works** | `tests/test_compare.py::TestTheReaderMatchesTheWriter`. The JSON output of an earlier run, identified by its `qedro` block; schema 0 is a document from 0.1 to 0.3 and is read with the difference stated (#14) |
| A spreadsheet register | **candidate** | The trigger is written down rather than left to feel: the first register somebody actually has that is a CSV. What its columns mean is a different question from the one `register.py` answers |

## Emitters — who produces what we read

**This column needs no work from us**, which is the point of the design. Anything
that emits OpenLineage is readable. The second and third columns are what change
the output.

| | Lineage | Art. 30 `processing` facet | `dataQualityAssertions` | `sourceCodeLocation` |
|---|---|---|---|---|
| dbt | **works** — openlineage-dbt 1.53.0, `tests/fixtures/dbt-1.53`, read in `tests/test_ropa.py::TestOrchestrationParents` | no | not in the captured `dbt-ol run`, which ran no tests | not in the capture |
| Airflow | **works** — provider 2.20.1 on Airflow 3.3.1, `tests/fixtures/airflow-3.3.1`, read in `tests/test_ropa.py::TestOrchestrationParents` | no | not in the capture; a Great Expectations operator would send it | not in the capture: the provider sent `sourceCode`, the bash command itself |
| Spark | **works** — openlineage-spark 1.53.0 on Spark 4.2.0, `tests/fixtures/spark-4.2.0`, read in `tests/test_ropa.py::TestOrchestrationParents` | no | not in the capture | not in the capture |
| Flink | **works** — Flink 1.20.5 with `openlineage-flink` 1.53.0, `tests/fixtures/flink-1.20.5`, read in `tests/test_ropa.py::TestOrchestrationParents` | no | not in the capture | not in the capture |
| Dagster, Trino | **candidate** | no | — | — |
| `pipeline-runtime` | **works** — `tests/fixtures/events`, read in `tests/test_cli.py::test_clean_read_earns_the_tombstone` | **works** — the only emitter that does; `tests/test_ropa.py::test_the_processing_facet_is_read_from_the_pipeline_runtime_capture` | **works** — `tests/test_quality.py::test_assertions_are_read_from_the_pipeline_runtime_capture` | no |
| Anything else, wrapped in [`art30-emit`](https://github.com/cordata-tech/art30-emit) | **works** — art30-emit 0.1.0, `tests/fixtures/art30-emit-0.1.0` | **works** — the second emitter that sends it, and the only one that is not `pipeline-runtime`; `tests/test_ropa.py::TestTheArt30EmitCapture` | — | — |

Each `works` in the first column is a real capture from that emitter, run through every
projection. Flink is the narrowest of them: its integration reads lineage from a short
list of connectors rather than from the job's plan, so a Flink job using anything else
emits a job with no datasets, and the capture also names the source only on `START`.

The other columns say what the capture contained rather than what the integration can
emit in some configuration. Until 2026-09-17 they said *emits it* for
`sourceCodeLocation` on dbt, Airflow and Spark, and none of the five captures carries
it. What the captures found is tracked in #8, #9, #22 and #23.

The gap in the second column is the product problem rather than a coverage
problem. A pipeline emitting lineage but no `processing` facet produces a record
that falls back on the mapping file, which is assertion rather than evidence.
Closing it needs a small vendor-neutral emitter for the published facet rather than
another source adapter, which is what
[`art30-emit`](https://github.com/cordata-tech/art30-emit) is: `declare(...)` around
the work, or `art30-emit … -- <command>` around a command that cannot be imported.
It reaches the systems no integration can — a Lambda, a stored procedure, a cron
job — rather than adding the facet to dbt or Airflow, where it would have to come
from those projects.

## Facets read

| | State | Needed by |
|---|---|---|
| `processing` (this repo's Art. 30 facet) | **works** | `ropa` — `tests/test_ropa.py::TestProvenancePrecedence`, and against the real `pipeline-runtime` capture; the key is held to that capture by `tests/test_facet_schema.py` |
| `dataQualityAssertions` (standard, input facet) | **works** | `quality` — `tests/test_quality.py::TestReadingTheFacet`, and against the real `pipeline-runtime` capture |
| `sourceCodeLocation` (standard, job facet) | **works** | `provenance` — `tests/test_provenance.py::TestWalkingBackwards::test_the_code_and_commit_come_from_the_standard_facet`. None of the five real captures carries it |
| `schema` (standard, dataset facet) | **works** | dataset columns — `tests/test_events.py::TestDatasets::test_field_names_come_from_the_schema_facet` |
| `tags` (standard, dataset facet) | **works** — read, including `field`-level tags — `tests/test_events.py::TestTheTagsDatasetFacet`, and from a real capture in `tests/test_ropa.py::TestTheArt30EmitCapture` | classification, for the Art. 30(1)(c)–(f) fields (#13). The spec has it and both clients generate it — `openlineage-python` ships `TagsDatasetFacet` from 1.52.0 — but **no integration emits it** as of 1.53.0: the repository builds job and run tag facets only, and none of the four captures from dbt, Airflow, Spark or Flink carries one. What is missing is an emitter: `art30-emit` sends it today, and `pipeline-runtime` is adding it (`cordata-tech/pipeline-runtime#3`) |
| `lifecycleStateChange` (standard, dataset facet) | **works** | `erasure`, as the instant an erasure happened — `tests/test_erasure.py::TestTheTombstone` and, against the demo estate,
`tests/test_erasure.py::TestTheDemoEstate` — spelled in full because
`tests/test_compare.py::TestTheDemoEstate` is a different class. `DROP`, `TRUNCATE` and `OVERWRITE` are read as erasures and `ALTER`, `CREATE` and `RENAME` are not, because a rename is not a deletion. **No integration emits it** as of 1.53.0: none of the five captures carries one, so the demo's erasure job is what exercises it. Where it is absent, `--since` supplies the instant and the record says it was asserted |
| `parent` (standard, run facet) | **works** | `ropa`, to leave orchestration parents out of the activities — `tests/test_ropa.py::TestOrchestrationParents`, against real dbt, Airflow and Spark lineage: the dbt invocation, the Airflow DAG run, and the Spark application run |
| A model version per run | **works** for the standard `tags` run facet (key `model_version`) and `cordata_provenance.step_params.*.model_version` | `ropa --view deployer` — `tests/test_deployer.py`, including against the captured `pipeline-runtime` event in `docs/evidence/`. There is **no standard facet** for this, which is why the list is short and documented |
| The application release behind what a run read | **works** for `cordata_provenance.source_published_by` and `.source_published_release`, with `source_schema_version` and `source_table` naming what was published — `tests/test_provenance.py::TestTheApplicationBehindWhatWasRead`. There is **no standard facet**: `datasetVersion` says which version a run read and never who published it, and `ownership` names owners of the dataset as a standing fact, with no release. The tests are synthetic — `tests/fixtures/events` was captured from pipeline-runtime 0.1.0 before `722ac7e` added the fields, so **no capture carries them yet**. Re-capture when a pipeline-runtime release emits them (#25) |
| A signed-commit report | **works** for `cordata_provenance`, `gitProvenance`, `provenance` | `provenance` — `tests/test_provenance.py::TestEverySignatureSpellingIsRead`. There is **no standard spelling** for this, which is why the common answer is *unknown* |
| Everything else | **works** | Nothing. Facets are raw dictionaries and unknown ones arrive intact — the shallow-model rule, and why this table is short; `tests/test_events.py::TestFacets::test_the_raw_event_survives_for_facets_nobody_modelled` |

## Classification vocabularies

`ropa` reports classification as of #13: categories of personal data and of data
subjects, residency and retention, read from the standard `tags` dataset facet and
resolved against the loaded vocabulary. The adapters below are ways a classification
could arrive from a catalog instead; they are adapters onto one vocabulary, never the
shape of the model.

**The trigger for building the first one, written down rather than left to feel: an
organisation whose classification lives in a catalog and *not* in the events.** #13 set
out expecting to need one and did not — the standard `tags` dataset facet carried
categories, subjects, residency and retention — so the demand that would justify a
catalog adapter has not appeared yet. The interface is extracted at the **second**
adapter, not the first: one member is not a set, and a shape fitted to whichever
catalog arrives first is how *source-neutral* quietly becomes *LakeFormation-shaped*.

**A catalog value is an assertion, not evidence, and the record has to say so.** A
catalog answers *what is the policy on this dataset right now*; an Art. 30 record
answers *what happened, and can I prove it*. A classification read today is not
evidence about a run in March, so it would arrive below `FACET` in the provenance
order and be marked as asserted wherever it printed — the same treatment the mapping
file gets. Wiring a current-state lookup in as though it were evidence is the mistake
this row exists to prevent.

| | State |
|---|---|
| A loaded vocabulary document (YAML / JSON / TOML) | **works** — `src/qedro/vocabularies/dsgvo.yaml`, `tests/test_vocabulary.py`. The shipped document carries `purpose`, `legal_basis`, and, for v0.3, `data_category`, `special_category` (closed on the Art. 9(1) list), `subject_type`, `residency` and `retention` |
| LakeFormation LF-tags | **candidate** — most likely to arrive through `catalog-mcp` (platform#26), which is LF-tag-native by design. That binding is correct there and must not reach this side |
| GCP Data Catalog policy tags | **candidate** |
| Purview classifications | **candidate** |
| OpenMetadata glossary terms | **candidate** |

## Output

| | State |
|---|---|
| text, markdown, json | **works** — `tests/test_render.py`, parametrised over format **and** projection |
| xlsx | **works** — `tests/test_xlsx.py` |
| CSV | **candidate** — trivial, and nobody has asked |
| PDF | **candidate** — an auditor asks for xlsx; this would be for the version somebody prints and signs |

## Python

| | State |
|---|---|
| 3.12, 3.13, 3.14 | **works** — CI runs all three |
| 3.11 and below | **no** — `datetime.fromisoformat` handles `Z` natively from 3.12, and adding a normalising workaround for older versions is a maintenance cost with no user behind it |

## Writing anywhere

| | State |
|---|---|
| Any write path into a system Qedro reads | **no** — read-only is a property of what the code can reach, not a policy. See [SECURITY.md](../SECURITY.md) |
