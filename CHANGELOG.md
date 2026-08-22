# Changelog

Notable changes, in the words of somebody deciding whether to upgrade.

`0.x` may change interfaces between releases. The entries below say which, and
output formats and the `qedro.yaml` schema are the parts most likely to move
before `1.0`.

## 0.1.0 — 2026-08-22

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

### `qedro quality` — the assertion history

- What was checked about each dataset and when, from the standard OpenLineage
  `dataQualityAssertions` facet that Great Expectations already emits.
- **Datasets with no assertions are half the artefact**, not a footnote: a
  dataset with no failures and a dataset with no checks look identical in every
  summary anybody writes, and they are opposites.
- A *failing* expectation does not withhold the mark. The mark says this account
  of what was checked is complete, not that the data is good.
- `--domain` narrows it, repeatably; `--days` is shorthand for the window.

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
