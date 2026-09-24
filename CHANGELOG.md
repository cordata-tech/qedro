# Changelog

Notable changes, in the words of somebody deciding whether to upgrade.

`0.x` may change interfaces between releases. The entries below say which, and
output formats and the `qedro.yaml` schema are the parts most likely to move
before `1.0`.

## 0.5.0 — 2026-09-24

A fourth projection, and the existing chain reaching one hop further out.

`qedro erasure` (#4) answers the part of Art. 17 that lineage is actually for. Finding
where a subject's data lives is a catalog's job and deleting it is an orchestrator's;
proving the deletion reached everything derived from it, and naming the places the
proof does not reach, is what the downstream closure of a dataset is. `provenance`
(#25) now names the application release behind the data a run read, rather than
stopping at the commit behind the pipeline.

Neither invents a facet. The erasure instant comes from the standard
`lifecycleStateChange`, and where nothing emitted one the record says the instant was
typed rather than proved.

- **`qedro erasure`** — what descends from a dataset somebody erased, and whether the
  erasure reached it (#4). Walks the lineage graph forwards from the erased dataset and
  reports every dataset derived from it, transitively, with whether a job rewrote each
  one afterwards. The descendants nothing rewrote are **named rather than counted**:
  that list is the output, and it is the answer Art. 17 conversations rarely give.
- **The tombstone is evidence or an assertion**, and no facet had to be invented for
  it. OpenLineage has `lifecycleStateChange`, whose `DROP`, `TRUNCATE` and `OVERWRITE`
  are erasures and whose `ALTER`, `CREATE` and `RENAME` are not — a rename is not a
  deletion. An emitted one is the instant somebody proved; `--since` is the same instant
  typed by hand, works against any lineage, and withholds the mark. Where both exist the
  emitted one wins and both are printed.
- **It reports datasets, not rows**, in every format and on runs that earn the mark as
  much as on runs that do not. It can show that a dataset descends from the erased one
  and that a job rewrote it afterwards; no lineage event says a particular data
  subject's rows are gone, and this never implies otherwise.
- **`provenance` names the application release behind the data a run read** (#25), one
  hop further out than the commit behind the pipeline. Read from
  `cordata_provenance.source_published_by` and `.source_published_release`, with
  `source_schema_version` and `source_table` naming what was published — so the step
  says *version 7 of fraud_raw.transactions, published by catalog-loader release
  2026.07.3* rather than leaving the claim floating.
- **An unknown publisher is counted, not a withholding reason.** The signature withholds
  because the chain claims authorisation and cannot show it; a missing publisher says
  nothing about authorisation, so it joins the commit and signature counts in the scope
  statement. The rule this settles, for the next field somebody adds: the mark is
  withheld for what the chain claims and counted for what it merely covers.
- **Absent reads as unknown, never as unpublished**, as the signature does. An unset
  field means the catalog recorded no producer for that version, or the run read
  nothing.
- **The demo estate carries an erasure**: `acme.crm/subject-erasure` overwrites
  `crm_raw.contacts` on 2026-07-22 and emits the lifecycle facet, so the evidenced path
  runs against committed events. Two of its three descendants were rewritten in time
  and the weekly dunning job was not, which is the hole the record names. The erasure
  job is itself in the Art. 30 record, because honouring a right is processing.

## 0.4.0 — 2026-09-20

Comparing two records without a database (#14), and checking a hand-maintained
register against one (#24). Both answer a question no single record can: a purpose
emitted by the pipeline and the same purpose typed into a mapping file are the same
string and a different claim, and only a comparison can say which one you have now.

Neither prints the mark. ∎ means *this artefact stands on its own evidence*, and a
comparison's evidence is two documents it cannot verify.

- **`qedro diff before.json after.json`** — what changed between two records, with no
  database between them (#14). The finding it exists for is invisible in either
  document alone: a purpose emitted by the pipeline and the same purpose read from
  the mapping file are the same string and a different claim, so the provenance
  order decides what counts as a loss of evidence, and `fraud-detection, unchanged —
  evidence lost: emitted facet → mapping file` is a finding rather than a silence.
  All four formats, and a JSON consumer gets `loses_evidence` stated rather than
  having to know how `Provenance` is ordered.
- **`qedro diff register.yaml record.json`** — where a hand-maintained register and
  the generated record disagree (#24). Same command, dispatching on what each side
  is, and the order of the two paths does not matter. The finding says which side
  rests on evidence: a register contradicting an emitted facet is a different problem
  from two hand-maintained documents disagreeing, and a register naming something the
  record has no field for is a third. Every finding carries the **owner** of the
  register row, which is what turns a list of disagreements into a list of things
  somebody can do.
- **A comparison prints no mark, in any format.** ∎ means *this artefact stands on
  its own evidence*, and a comparison's evidence is two documents it cannot verify.
  It reports each record's own verdict instead — so a field that was wrong in both
  records is reported as unchanged, and unchanged is not the same as correct.
- **What is comparable is said before anything else**: a different source, and
  windows that are identical, overlapping, adjacent, disjoint or unknown. The one
  refusal is two documents of different shape. A difference in coverage is reported
  as a difference in coverage and never attributed to a particular finding, because
  that attribution would be a guess wearing a caveat.
- **A field the register does not carry is not a disagreement.** A register is a
  partial document by nature — it says nothing about residency or retention — and
  reporting everything it omits would bury the findings that matter. Nor is a
  difference of provenance between the two sides: a register is declared and a record
  evidenced by construction, so that is what the two documents *are*.
- **Art. 30 content is compared, volume is not.** Runs, events and timestamps differ
  between any two windows, and reporting them would bury the findings that matter
  under arithmetic — both numbers are already in the two scope statements.
- **Every JSON document says what it is**, in a `qedro` block at the top: `schema`
  (an integer, 1, which changes only when a consumer reading the old shape would now
  be wrong), `projection`, `view` where there is one, and the `version` that produced
  it. `qedro diff` (#14) has to refuse two documents of different shape, and it can
  only refuse what it can name — inferring the projection from which keys are present
  is a guess. There is deliberately **no generation timestamp**: two runs over the
  same events produce the same bytes, or every diff reports a change that is not a
  change in processing.
- **Breaking, deployer view JSON:** the top-level `"view": "deployer"` key is now
  `qedro.view`. Which document this is has one spelling rather than two.
- **`demo/register.yaml`**, four rows and four ways a register drifts: one still true,
  one whose purpose the pipeline changed, one for a pipeline that no longer exists,
  and one naming a model version no run ever reported. `docs/evidence/register-drift.md`
  is that comparison captured, and CI now checks both transcripts against what the
  commands actually print.
- **Real Flink lineage as a test fixture**, `tests/fixtures/flink-1.20.5`: Flink 1.20.5
  with `openlineage-flink` 1.53.0 and a Kafka topic on each side. The capture names its
  source on `START` and no datasets at all on the terminal event, which is what an
  activity's datasets being gathered across a job's events now has a fixture for.
- **The `processing` facet has a second implementation**, and the docs point at it:
  [`art30-emit`](https://github.com/cordata-tech/art30-emit) puts the facet on the
  wire from code no integration reaches — a Lambda, a stored procedure, a cron job —
  as a context manager or a command wrapper. Nothing in this package changes;
  `docs/art30-facet.md` and `docs/compatibility.md` stop describing that emitter as
  wanted and start linking to it.
- **Its events are a fixture here too**, `tests/fixtures/art30-emit-0.1.0`, because a
  `works` row has to be named by a test in this repository rather than in the thing it
  is a claim about. It is the first capture carrying a `tags` dataset facet from a
  real emitter — no integration sends one as of 1.53.0 — so the Art. 30(1)(c)–(f)
  path is no longer exercised against generated events alone, and the first where one
  activity classifies what it reads and what it writes differently.
- **`1 of 1 dataset carries no classification`**, not `carry`. The noun agrees with the
  total and the verb with the count, and the Flink capture — one job, one dataset — is
  where that showed.

## 0.3.0 — 2026-09-19

The rest of Art. 30(1) that evidence can supply (#13). The record stops covering two
of the seven items the regulation lists and starts covering all seven, with the two
nothing emits marked as assertions wherever they appear.

- **The vocabulary carries the classification terms** an Art. 30 record needs:
  `data_category` and `subject_type` open, because the categories an organisation
  processes and whose data it holds are its own; `special_category` closed on the
  Art. 9(1) list, for the same reason `legal_basis` is closed on Art. 6(1);
  `residency` and `retention` from the reference ontology. Every value says what it
  means, because a list of values without that is a dropdown rather than an ontology.
- **The demo estate carries classification**, in both tiers: the datasets emit the
  standard `tags` facet, so the record reports categories, data subjects, residency and
  retention. Two datasets carry none on purpose — a vendor feed and a table nobody got
  round to — because an estate where everything is classified is not an estate anybody
  has, and the record has to say which is which.
- **The two items nothing emits can be asserted**: Art. 30(1)(d) categories of
  recipients and (g) security measures, in a `jobs:` rule or in the declared-activities
  document. Every format marks them as declared, and asserting them does not withhold
  the mark — there is no evidenced case to fall short of. The Art. 30(1) line now says
  the record has a field for all seven items, and which two can only ever be declared.
- **The Art. 30 record reports what the data is**, from the standard `tags` dataset
  facet: categories of personal data and of data subjects, residency and retention,
  each with the datasets that carried it and which side they were on. Nothing is
  inferred from a column name, a classification is never carried from one dataset to
  another, and the datasets that carry none are counted and named — *nobody said* is
  not *no personal data*. A value outside a closed term withholds the mark; a missing
  classification does not. The scope statement counts how many activities report a
  value for each item, because a field is not an answer.
- **The reader reads the standard `tags` dataset facet**, including `field`-level tags
  that classify one column. The spec has carried it since `1-0-0` and the clients
  generate it, but no OpenLineage integration emits it as of 1.53.0, so absent means
  nothing reported it, never that nothing applies.

## 0.2.0 — 2026-09-18

> **First public release**, and the first version on PyPI.
>
> **0.1.0 was never released.** It was tagged locally on 2026-08-22 and deliberately
> not published, so that Qedro could first be run against real work. That run found
> the orchestration-parent, guessed-domain, Art. 30(1), file-naming and read-only
> changes below, and publishing 0.1.0 would have shipped a record that overstated
> what it covers. Everything that was in 0.1.0 is included in this entry, and there
> is no separate 0.1.0 to upgrade from.

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
- **Activities that read datasets and wrote none are named** on a `read only` line in
  the Art. 30 scope statement, and in JSON as `scope.read_only`. They stay listed, and
  the mark is not withheld for them. Found against real Spark lineage, where the
  integration emits a job for each schema-reading action.
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
