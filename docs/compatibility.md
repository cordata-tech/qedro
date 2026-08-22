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

## Emitters — who produces what we read

**This column needs no work from us**, which is the point of the design. Anything
that emits OpenLineage is readable. The second and third columns are what change
the output.

| | Lineage | Art. 30 `processing` facet | `dataQualityAssertions` | `sourceCodeLocation` |
|---|---|---|---|---|
| dbt | **works** | no | emits it | emits it |
| Airflow | **works** | no | via the GX integration | emits it |
| Spark | **works** | no | via the GX integration | emits it |
| Flink, Dagster, Trino | **candidate** | no | — | — |
| `pipeline-runtime` | **works** | **works** — the only emitter that does | **works** | no |
| Anything else, via a few lines | — | **candidate** | — | — |

The gap in the second column is the product problem rather than a coverage
problem. A pipeline emitting lineage but no `processing` facet produces a record
that falls back on the mapping file, which is assertion rather than evidence.
Closing it needs a small vendor-neutral emitter for the published facet, not
another source adapter.

## Facets read

| | State | Needed by |
|---|---|---|
| `processing` (this repo's Art. 30 facet) | **works** | `ropa` |
| `dataQualityAssertions` (standard, input facet) | **works** | `quality` |
| `sourceCodeLocation` (standard, job facet) | **works** | `provenance` |
| `schema` (standard, dataset facet) | **works** | dataset columns |
| A signed-commit report | **works** for `cordata_provenance`, `gitProvenance`, `provenance` | `provenance`. There is **no standard spelling** for this, which is why the common answer is *unknown* |
| Everything else | **works** | Nothing. Facets are raw dictionaries and unknown ones arrive intact — the shallow-model rule, and why this table is short |

## Classification vocabularies

Relevant once a projection reports classification; none does yet. These are
adapters onto one vocabulary, never the shape of the model.

| | State |
|---|---|
| A loaded vocabulary document (YAML / JSON / TOML) | **works** — `src/qedro/vocabularies/dsgvo.yaml`, `tests/test_vocabulary.py` |
| LakeFormation LF-tags | **candidate** |
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
