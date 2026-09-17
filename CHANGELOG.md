# Changelog

Notable changes, in the words of somebody deciding whether to upgrade.

`0.x` may change interfaces between releases. The entries below say which, and
output formats and the `qedro.yaml` schema are the parts most likely to move
before `1.0`.

## 0.1.0 — unreleased

> Tagged and complete, and deliberately not published. The decision on
> 2026-08-22 was to run it against real work first and let it mature before
> anything is shown publicly — so the code below exists and the artefact does
> not. The date goes in when the tag is pushed.

First release. Three projections over OpenLineage, four output formats, and no
adoption of anything required beyond lineage a platform already emits.

### The reader

- `qedro events` reads a directory of `.json`, `.ndjson` or `.jsonl`, walking
  nested directories, or any Marquez-compatible HTTP API. Any spelling of the
  address works — a bare host, `.../api/v1`, or the full endpoint.
- The window is passed to the backend **and applied again to what comes back**,
  so a backend that ignores it produces a correct result rather than a quietly
  wider one.
- Reading stops after 10,000 events and says so, rather than returning a prefix
  of the history that looks like all of it.
- Malformed records are skipped and counted, never raised on, and the count
  reaches the completeness decision.
- Read-only by construction: `GET` is the only verb the code can build. A token
  comes from `QEDRO_API_TOKEN` and never from the command line, where it would
  land in shell history and in `ps`.

### `qedro ropa` — the Art. 30 record

- One activity per job, with the purpose and lawful basis that job declared and
  **where each field came from**. A value from an emitted facet is evidence; the
  same string from `qedro.yaml` is an assertion, and the two never merge.
- A facet always beats the mapping file. A config that could silently rewrite
  emitted evidence would make the record unfalsifiable.
- `qedro.yaml` — controller, domains and job patterns — read as YAML, JSON or
  TOML, with no behaviour depending on which.
- The Art. 30 processing facet is published as a spec in
  `schemas/openlineage-art30-processing-facet.json`, generated from
  `pipeline_runtime.descriptor.Processing` rather than written beside it.
- **Orchestration parents are not listed as activities.** A job whose run is named
  as a parent through the standard `ParentRunFacet`, and which read and wrote nothing
  and carries no `processing` facet, is named in the scope statement instead. The job
  count still includes it, and it does not withhold the mark. Found against real dbt
  lineage, where the invocation job showed up as an extra activity.
- **File datasets print as a URI**, `file:///data/raw/orders.csv`, instead of
  `file//data/raw/orders.csv`. The Airflow provider and the Spark integration emit
  the bare namespace `file` where the OpenLineage naming conventions give
  `file://{host}`, and an absolute path as the name; a name that starts with `/` is
  no longer given a second one, which also covers HDFS. No other dataset key
  changes, and `provenance --dataset` accepts the new spelling, the file name alone,
  or the old spelling.
- **Real Airflow and Spark lineage as test fixtures**, beside the dbt capture:
  Airflow 3.3.1 with the OpenLineage provider 2.20.1, and Spark 4.2.0 with
  openlineage-spark 1.53.0. The parent rule leaves out the Airflow DAG run and the
  Spark application run. `docs/compatibility.md` now names the captures, and no
  longer says dbt, Airflow and Spark emit `sourceCodeLocation`, which none of the
  captures carries.
- **The Art. 30 record states which Art. 30(1) items it has fields for**, on every
  run including one that earns the mark: (a) the controller and (b) the purposes, and
  none for (c) to (g). It is a scope line rather than a reason to withhold the mark,
  because it would otherwise fire on every run. JSON carries `scope.art30` as lists of
  covered and not covered letters. The deployer view does not repeat it.
- The text scope statement wraps long values under the value instead of running past
  the terminal width.
- **A guessed domain is said to be guessed.** When `domains:` is set, the scope
  statement names the domains guessed from the job namespace and those set by a
  rule's `domain:`, and the silent-domain reason names the guess and the override.
  JSON carries `domains_guessed`, `domains_mapped`, and a `domain_source` per
  activity. Found against real dbt lineage, whose default namespace `dbt` made a
  declared domain look silent.
- `--activities` reads a separate document of **declared activities**, meaning
  processing that emits no lineage. They appear beside the evidenced activities with
  every field marked `declared` and `no lineage` where the events would have spoken,
  are counted on their own line in the scope statement without changing the evidenced
  counts, and withhold the mark. The out-of-view sentence is reworded so that it is
  true whether or not anything is declared.

### `qedro ropa --view deployer` — the same record, per AI use case

- For each activity whose runs reported a model version: purpose and legal basis,
  the model versions with their run counts and dates, the inputs the latest run read,
  and the span of run records in view.
- Built from the Art. 30 record object, so purpose and legal basis are the record's
  own entries with their provenance, not a second reading of the events.
- The model version is read from the standard OpenLineage `tags` run facet (key
  `model_version`) or from `cordata_provenance.step_params`, where `pipeline-runtime`
  puts it.
- Art. 26 of the AI Act is cited from the consolidated text (CELEX
  02024R1689-20260727) with its condition: Annex III high-risk systems, from
  2 December 2027. The view does not decide whether a use case is high-risk.
- Retention is reported as the span of run records in view, never as a retention
  policy, and a short span does not withhold the mark.
- Declared activities that name a `model` are listed as AI use cases, marked
  `declared, no lineage`, and withhold the mark.

### `qedro quality` — the assertion history

- What was checked about each dataset and when, from the standard OpenLineage
  `dataQualityAssertions` facet that Great Expectations already emits.
- **Datasets with no assertions are half the artefact**, not a footnote: a
  dataset with no failures and a dataset with no checks look identical in every
  summary anybody writes, and they are opposites.
- A *failing* expectation does not withhold the mark. The mark says this account
  of what was checked is complete, not that the data is good.
- `--domain` narrows it, repeatably; `--days` is shorthand for the window. The scope
  statement names the filter and how many datasets it left out, in which domains, and
  whether each domain was guessed from the job namespace. A filter that leaves out
  every dataset says so, instead of reporting that no datasets were found.

### `qedro provenance` — the chain back to a commit

- Walks backwards from a dataset through the runs that produced it, the code
  each run executed and the commit it was at, using the standard
  `sourceCodeLocation` facet that dbt, Airflow and Spark all emit.
- **Unknown is not unsigned.** OpenLineage has no standard place for whether a
  commit was signed, so silence is a third state: it withholds the mark exactly
  as a failed signature would and is never rendered as one. `json` emits `null`,
  not `false`.
- A chain ends for three different reasons — a genuine source, a producing run
  outside the window, or the depth limit — and each is counted and named.
- An ambiguous `--dataset` is answered with the candidates rather than a guess.

### Output

- `text`, `markdown`, `json` and `xlsx`. The format follows `--out`'s filename
  unless `--format` says otherwise.
- **xlsx puts the verdict above the table on the first sheet.** A caveat below
  the data is a caveat nobody reads.
- Every format states the scope of what was looked at, on every run including
  one that earns the mark.

### The mark

- `∎` is printed only when an artefact stands on its own evidence, and the
  reasons for withholding it are always printed with it. `--no-symbol`, or
  `QEDRO_NO_SYMBOL=1`, for terminals with no glyph for U+220E.

### Also

- `demo/` — three weeks of synthetic lineage from dbt, Airflow and Spark, with
  no AWS anywhere in it, in two estates that differ only in whether the
  pipelines declare their Art. 30 fields.
- Apache-2.0. Python 3.12, 3.13 and 3.14.
