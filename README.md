<img src="docs/wordmark.svg" alt="Qedro" width="220">

**Turns emitted evidence into the artefacts an auditor asks for.**

Point it at OpenLineage events you already emit. Get back a DSGVO Art. 30 record of
processing activities, an assertion history, and the provenance chain from a published
number to the signed commit that authorised it.

```console
$ qedro ropa ./lineage --since 2026-01-01 --out ropa.xlsx
  wrote ropa.xlsx                                                              ∎
```

> [!NOTE]
> Early development. All three projections work, in four output formats. Interfaces
> may still move. Watch the repository rather than depending on it.

## Try it

[`demo/`](demo/) holds a committed synthetic estate — three weeks of dbt, Airflow
and Spark lineage from a company that does not exist, with no AWS anywhere in it.

```console
$ qedro ropa demo/lineage --config demo/qedro.yaml            # asserted, no mark
$ qedro ropa demo/lineage-declared --config demo/qedro.yaml   # evidenced      ∎
```

Same jobs, same runs, same three weeks. The only difference between the two
estates is whether the pipelines declare their purpose and lawful basis — and it
is the difference between a record somebody asserts and a record that stands on
its own evidence. [`demo/README.md`](demo/README.md) walks through it.

## The Art. 30 record

`qedro ropa` produces one activity per job, with the purpose and lawful basis that
job declared — and **where each field came from**. That last part is the difference
between this and a register somebody maintains by hand:

```console
$ qedro ropa ./lineage
Record of processing activities — ACME Finanz GmbH
  contact: dpo@acme.example

  acme.fraud/transactions-scored-daily
    purpose       fraud-detection
    legal basis   legitimate-interest
    reads         wh/fraud_raw.transactions
    writes        wh/fraud_curated.scores
    runs          14 in window, last 2026-03-01T02:15:00+00:00

  acme.fraud/transactions-scored-daily.validate
    purpose       data-quality-validation (mapping)
    legal basis   legitimate-interest (mapping)
    ...
```

A value marked `(mapping)` came from `qedro.yaml` rather than from an emitted facet.
It is an assertion by whoever wrote the file, not evidence produced by the thing that
ran, and the tombstone is withheld for the whole record when any entry relies on one.

**Every run states its own scope**, including a run that earns the mark:

```console
  Scope of this record
    source        ./lineage
    window        2026-01-01T00:00:00+00:00 to 2026-03-01T02:15:00+00:00
    in view       47 jobs, 112 datasets, 1,284 events
    provenance    41 evidenced, 6 from the mapping file, 0 undeclared
    silent        marketing (in scope, no lineage)
    This record covers processing performed by pipelines that emit lineage.
    Systems that do not emit lineage — CRM, HR, ticketing, marketing tools,
    anything on paper — are not represented here, and their absence from this
    record is not evidence of their absence from the organisation.
```

That paragraph is not boilerplate. Art. 30 covers everything a controller processes,
and pipelines are a subset of that — so what this produces is a complete record of
the **pipeline-borne subset**, never the whole thing. Printing it only when something
went wrong would teach a reader that its absence means full coverage.

### Output

`--format text|markdown|json|xlsx`, and `--out` to write a file. The format follows
the filename when you do not say — `--out ropa.xlsx` is a workbook, `--out ropa.md`
is markdown — and an explicit `--format` always wins.

**xlsx is the one an auditor asks for**, and it is the only output that has to
survive being forwarded. Two sheets: the activities, and the scope. The verdict
sits above the table on the first sheet rather than behind it, because a caveat
below the data is a caveat nobody reads — the same failure this tool exists to
prevent, reproduced in its own output. Where a value came from is a column of
words; the tint on a cell is reinforcement and never carries the meaning alone.

### Configuration

`qedro.yaml` beside the working directory, or `--config`. **YAML, JSON and TOML all
work** — nothing in the tool depends on which you chose.

```yaml
controller:
  name: ACME Finanz GmbH
  contact: dpo@acme.example

domains:            # named here, so a domain that emitted nothing is visible
  - fraud           # in the output instead of silently absent
  - marketing

jobs:               # the fallback, for pipelines that emit no facet
  "acme.fraud/*":
    purpose: fraud-detection
    legal_basis: legitimate-interest
```

Patterns are fnmatch against `namespace/name` and then the bare name, first match in
file order winning. A facet always beats the file: a config cannot silently rewrite
what a pipeline emitted.

### The vocabulary is a document, not an enum

The six Art. 6(1) bases live in a YAML file the tool loads at runtime, not in Python.
Point `--vocabulary` at your own and the shipped one is replaced wholesale — which is
what makes an organisation's own ontology possible later without a rewrite. A value
outside a closed term is flagged and still reported; refusing to read what an emitter
actually sent would hide the finding that matters.

### The deployer view

`--view deployer` shows the same record per AI use case, answering the questions the
EU AI Act puts to a deployer — an organisation using a model somebody else built. For
each activity whose runs reported a model version, it lists the purpose and legal
basis, the model versions with their run counts, the inputs the latest run read, and
the span of run records in view:

```console
$ qedro ropa demo/lineage-declared --config demo/qedro.yaml --view deployer
  acme.fraud/transactions-scored-daily  (fraud)
    purpose                  fraud-detection
    legal basis              legitimate-interest
    model version            2026-06-fraud-v3    7 runs, 2026-06-15 to 2026-06-21
                             2026-05-fraud-v2   14 runs, 2026-06-01 to 2026-06-14
                             reported in the tags run facet
    ...
```

The view is built from the Art. 30 record object rather than from the events a second
time, so each use case holds the record's own purpose and legal basis, with the same
provenance, and the two views cannot disagree about them. The events supply only what
the Art. 30 record does not carry: the model version per run, and what each run read.
The reasoning behind making this a view of `ropa` rather than a separate command is
recorded on [#7](https://github.com/cordata-tech/qedro/issues/7).

Three limits are stated in every format rather than left to the reader:

- **Art. 26 is cited with its condition.** The deployer duties apply to high-risk
  systems listed in Annex III from 2 December 2027, cited from the consolidated text
  (CELEX 02024R1689-20260727). Nothing in the events says whether a system is
  high-risk, so the view does not decide it.
- **Retention is the span of run records in view**, not a retention policy, which the
  events do not carry. Art. 26(6) sets a minimum period for logs, and DSGVO storage
  limitation pulls the other way for personal data, so the view reports the span and
  resolves neither. A short span does not withhold the mark, because withholding it
  would imply Art. 26(6) applies today.
- **Declared use cases are marked as declared.** Most AI use outside engineering teams
  emits no lineage, for example staff pasting text into a vendor's assistant.
  `--activities` reads a separate document of such uses; every entry is shown as
  `declared, no lineage` and withholds the mark. For now the flag works with
  `--view deployer` only, and bringing declared activities into the Art. 30 view is
  [#6](https://github.com/cordata-tech/qedro/issues/6).

The model version is read from two documented places: the standard OpenLineage `tags`
run facet with key `model_version`, and `step_params.<step>.model_version` in the
`cordata_provenance` facet that `pipeline-runtime` emits. An activity whose runs report
neither is counted in the scope statement and not listed.

## The assertion history

`qedro quality` reports what was actually checked about each dataset, and when — and
it gives equal weight to what was not:

```console
$ qedro quality demo/lineage --config demo/qedro.yaml
  warehouse/fraud_curated.transactions_scored  (fraud)
    asserted by   acme.fraud/scores-validated
    runs          20 in window, last 2026-06-21T02:51:00+00:00
    expectations  5 — 4 held, 1 failed
      held    expect_column_values_to_be_unique on tx_id           20 runs
      FAILED  expect_table_row_count_to_be_between                 20 runs, 2 failed, last 2026-06-10

  Not checked — 10 datasets carry no assertions at all
    warehouse/billing_raw.orders
    ...
```

**A dataset with no failures and a dataset with no checks look identical in every
summary anybody writes, and they are opposites.** So the unchecked list is half the
artefact rather than a footnote, and it is a reason the mark is withheld.

A *failing* expectation is not. The mark says this account of what was checked is
complete, not that the data is good — and withholding it for a failure would give
somebody a reason to stop emitting the assertion that fails.

The evidence is the standard OpenLineage `dataQualityAssertions` facet, which Great
Expectations already emits. Nothing Cordata-specific is involved.

`--domain fraud` narrows it, repeatably, and `--days 90` is shorthand for the window.

## The provenance chain

`qedro provenance` answers the question a published number provokes — where did this
come from, and who authorised it? It walks backwards: the run that produced the
dataset, the code that run executed, the commit it was at, and then the same for
everything that run read.

```console
$ qedro provenance demo/lineage --dataset billing_curated.dunning_cases
  warehouse/billing_curated.dunning_cases
    produced by   acme.billing/dunning-weekly
    code          https://github.com/acme-finanz/data-platform at b7eb23bd289c
                  main models/billing/dunning_cases.sql
    signature     signature unknown — nothing reported it

    warehouse/billing_curated.invoices
      produced by   acme.billing/invoices-nightly
      ...

      warehouse/crm_raw.contacts
        — nothing in the window produced it
```

**Unknown is not unsigned.** OpenLineage has a standard place for the code identity —
`sourceCodeLocation`, which dbt, Airflow and Spark all emit — and no standard place at
all for whether that commit was signed. So silence is reported as a third state. It
withholds the mark exactly as a failed signature would, and it is never rendered as
one: saying *this ran under an unsigned commit* when nobody reported either way would
be inventing evidence.

**A chain that ends is not a chain that is complete.** The walk stops for three
different reasons — a genuine source dataset, a producing run outside the window, or
the depth limit — and each is counted and named, because in the output they look
identical.

Nothing here calls a forge API to resolve a commit. Read-only is a property of what
the code can reach.

## The reader

Worth running on its own before anything else — it tells you whether your lineage is
readable at all:

```console
$ qedro events ./lineage
  1,284 events · 37 jobs · 112 datasets · 14 files                             ∎
  complete 641, start 641, fail 2
```

Point it at a directory of `.json`, `.ndjson` or `.jsonl`. It reads newline-delimited
events, JSON arrays and single objects without being told which, walks nested
directories, and never stops on a bad record — malformed events are counted and
reported rather than thrown.

Or point it at a Marquez-compatible API and it reads the same events over HTTP:

```console
$ qedro events https://marquez.internal --since 2026-01-01
  4,102 events · 37 jobs · 112 datasets · 42 pages                             ∎
```

Any spelling of the address works — a bare host, `.../api/v1`, or the full endpoint.
The window is passed to the backend as a query and **applied again to what comes
back**, so a backend that ignores it still produces a correct result rather than a
quietly wider one. Reading stops after 10,000 events, and says so, rather than
returning a prefix of the history that looks like all of it.

The HTTP source is read-only by construction: GET is the only verb the code can
build. If the backend needs a token, it comes from `QEDRO_API_TOKEN` and never from
the command line, where it would land in shell history and in `ps`.

If anything was unusable the tombstone is withheld and the reason goes to stderr:

```console
$ qedro events ./lineage
  1,282 events · 37 jobs · 112 datasets · 14 files
  complete 640, start 641, fail 1
  ! 2 records were not usable OpenLineage events
```

Use `--no-symbol`, or `QEDRO_NO_SYMBOL=1`, where U+220E has no glyph.

## The Art. 30 facet

Lineage answers *what happened*. Art. 30(1)(b) asks for the **purposes of the
processing**, and no graph of jobs and datasets contains them — whether a customer
table is processed under consent or under legitimate interest is not derivable, it has
to be declared by someone who knows.

So this repository publishes the declaration as an OpenLineage job facet:
[`schemas/openlineage-art30-processing-facet.json`](schemas/openlineage-art30-processing-facet.json),
documented in [docs/art30-facet.md](docs/art30-facet.md). Two fields, `purpose` and
`legal_basis`, under the `processing` key. Nothing in it is Cordata-specific; any
emitter that can attach a custom job facet can produce it.

The schema is **generated** from `pipeline_runtime.descriptor.Processing` rather than
written beside it, and a test fails when the two diverge. One governance model with
several consumers is a claim this project makes in public, so a consumer that quietly
restates the model would be a counterexample sitting in the repository the claim
cites.

## The name

**Q.E.D.** — *quod erat demonstrandum*, "that which was to be demonstrated". The phrase
that closes a proof.

It is not decoration. [Art. 5(2) GDPR](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679)
places a duty on the controller to be able to **demonstrate** compliance — not to
achieve it quietly, but to show it on request. That is a *demonstrandum*, and producing
it from evidence rather than from assertion is the entire job of this tool.

Mathematicians stopped writing Q.E.D. some time ago. Paul Halmos borrowed a solid square
from magazine typography instead, and it became standard — the **tombstone**, or *halmos*.
It is [U+220E END OF PROOF](https://en.wikipedia.org/wiki/Q.E.D.#Typography), **∎**.

The wordmark puts it where the final letter would go:

```
QEDR∎
```

And it means something at runtime. **The CLI prints `∎` only when the artefact stands on
its own evidence** — never when a job fell back to a mapping file for its `purpose`, and
never when a domain in scope produced no lineage in the window. The run still succeeds
and still writes the file; it simply does not claim to be a proof.

So a complete run finishes the product's name.

## Why this exists

A compliance artefact with holes in it is worse than none, because the holes are
invisible. A RoPA assembled by hand from a wiki, a Confluence page and somebody's memory
looks exactly like one derived from what the platform actually did.

The argument is set out across four posts on [cordata.tech](https://cordata.tech):

- [Fabric + Mesh on AWS](https://cordata.tech/en/blog/fabric-mesh-on-aws) — the account topology and the LF-tag ontology
- [Behaviour-first governance in practice](https://cordata.tech/en/blog/behaviour-first-governance-in-practice) — governance artefacts as byproducts of behaviour
- [A pipeline is a descriptor, not a program](https://cordata.tech/en/blog/pipelines-as-descriptors) and [part 2](https://cordata.tech/en/blog/pipeline-half-openlineage-gx) — the evidence a pipeline emits
- [The catalog is the API](https://cordata.tech/en/blog/governed-mesh-over-mcp) — the read path over that evidence

This is the part those posts stop short of: the code that reads the evidence and produces
the artefact.

## Design commitments

**No adoption required.** It reads OpenLineage from a directory of JSON or a
Marquez-compatible API. dbt, Airflow, Spark, Flink and Dagster already emit it. Nothing
here needs Cordata's descriptor model, though richer facets produce richer output.

**Not bound to one cloud.** Classification is a source-neutral vocabulary; LakeFormation
LF-tags are one adapter alongside GCP Data Catalog policy tags and Purview
classifications. If `qedro ropa` cannot run against a Marquez instance with no AWS
anywhere in the picture, the neutrality is decorative — so that is an actual test
(`tests/test_cli.py::TestRopaAgainstAnApi`), not an aspiration.

**Flexible by construction, everywhere it is cheap to be.** Multi-cloud, multi-pipeline,
multi-format. Sources are a directory or any Marquez-compatible API; config and
vocabulary documents are YAML, JSON or TOML; facets stay raw dictionaries so an emitter
nobody anticipated still arrives intact. Each of these was chosen at the point where
picking one option would have cost nothing today and a rewrite later.

**The vocabulary is data, not types.** Organisations define their own ontologies. Nothing
is compiled against a fixed set of sensitivity levels.

**Read-only by construction.** No write path, no credentials that could acquire one.

## Documentation

| | |
|---|---|
| [`demo/README.md`](demo/README.md) | the three tiers, walked through against a real estate |
| [`docs/art30-facet.md`](docs/art30-facet.md) | the Art. 30 facet, for anyone who wants to emit it |
| [`docs/compatibility.md`](docs/compatibility.md) | what this runs against, and what it does not |
| [`docs/evidence/`](docs/evidence/) | captured runs that published writing quotes, and how each was produced |
| [`CHANGELOG.md`](CHANGELOG.md) | what changed, in the words of somebody deciding whether to upgrade |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | scope, and the four commitments that must not erode |
| [`SECURITY.md`](SECURITY.md) | what the tool can reach, by construction |

## Licence

[Apache-2.0](LICENSE). Everything, including the parts that would be the commercial
tier elsewhere.
