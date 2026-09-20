<img src="docs/wordmark.svg" alt="Qedro" width="220">

[![CI status on main](https://github.com/cordata-tech/qedro/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/cordata-tech/qedro/actions/workflows/ci.yml)
[![qedro on PyPI](https://img.shields.io/pypi/v/qedro)](https://pypi.org/project/qedro/)
[![Python versions qedro runs on](https://img.shields.io/pypi/pyversions/qedro)](https://pypi.org/project/qedro/)
[![Licence: Apache-2.0](https://img.shields.io/badge/licence-Apache--2.0-blue)](LICENSE)

**Turns emitted evidence into the artefacts an auditor asks for.**

Point it at OpenLineage events you already emit. Get back a GDPR Art. 30 record of
processing activities, an assertion history, and the provenance chain from a published
number to the signed commit that authorised it.

The GDPR is the EU's data protection regulation, [Regulation (EU) 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj),
known in German as the *DSGVO*. Its Article 30 requires an organisation that processes
personal data, or processes it on another's behalf, to keep a written record of its
processing activities: who is responsible, for what purposes, which categories of people
and data, who receives it, and more. Supervisory authorities can ask to see that record,
and Qedro generates the parts of it that lineage can evidence.

```console
$ qedro ropa ./lineage --since 2026-01-01 --out ropa.xlsx
  wrote ropa.xlsx                                                              ∎
```

> [!NOTE]
> Early development. All three projections work, in four output formats, and the test
> suite runs against real lineage captured from dbt, Airflow and Spark. `0.x`
> interfaces may still move between releases, and [`CHANGELOG.md`](CHANGELOG.md) says
> which.

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
    Art. 30(1)    this record has fields for (a) the controller and (b) the purposes,
                  and none for (c) categories of data subjects and of personal data, (d)
                  categories of recipients, (e) transfers to third countries, (f) time
                  limits for erasure and (g) security measures
    domains       fraud, billing guessed from the job namespace
    silent        marketing (in scope, no lineage)
    This record covers processing performed by pipelines that emit lineage, and any
    activities declared with no lineage. Systems that do not emit lineage — CRM, HR,
    ticketing, marketing tools, anything on paper — are not represented here unless
    they are declared, a declared activity is an assertion rather than evidence, and
    the absence of anything else from this record is not evidence of its absence
    from the organisation.
```

That paragraph is not boilerplate. Art. 30 covers everything a controller processes,
and pipelines are a subset of that — so what this produces is a complete record of
the **pipeline-borne subset** plus whatever has been declared, never the whole thing.
Printing it only when something went wrong would teach a reader that its absence means
full coverage.

The `Art. 30(1)` line is the same kind of statement about fields rather than systems.
Art. 30(1) GDPR lists seven items a controller's record contains, and this record has
fields for two of them. A record whose every activity is evidenced still earns `∎`,
because the mark says the record stands on its own evidence, not that it holds every
item, so the line is printed on every run instead. It states what the record contains
and does not judge whether that is sufficient. The legal basis the record also prints is
not one of the seven items. Deriving (c) to (f) from classification is planned for
v0.3 ([#13](https://github.com/cordata-tech/qedro/issues/13)).

### Orchestration parents are not activities

dbt emits a job for each invocation as well as one per model, and Airflow and Spark
emit a job for a DAG run or an application run in the same way. When a job's run is
named as the parent of other runs in view, through the standard OpenLineage
`ParentRunFacet`, and the job itself read and wrote nothing and declares no purpose,
it is left out of the activity list and named in the scope statement instead:

```console
    in view       5 jobs, 4 datasets, 10 events
    parents       1 job not listed as an activity — a parent run with no datasets and no
                  processing facet: dbt/dbt-run-dbtprobe
```

A parent that has datasets of its own, or declares purpose and legal basis, stays
listed. The match is on the parent's run id, not on the job's name, so nothing depends
on dbt's naming. A backend that drops the `parent` facet, as Snowflake's external
lineage does, leaves the invocation listed. The reasoning is on
[#8](https://github.com/cordata-tech/qedro/issues/8).

A job that read datasets and wrote none stays listed, and is named on its own line.
Spark's integration emits one such job for each action it runs to infer a schema, and
the events do not tell those apart from a real job that only reads, such as an export
or a monitoring count. Which of them is a processing activity is left to the reader:

```console
    read only     3 activities read datasets and wrote none:
                  default/orders_enrichment.collect_limit,
                  default/orders_enrichment.deserialize_to_object,
                  default/orders_enrichment.map_partitions_parallel_collection
```

### What the data is

Art. 30(1) asks for more than the purpose. Where the datasets an activity touched carry
the standard OpenLineage `tags` facet, the record reports what that says: categories of
personal data, categories of data subjects, where the data sits, and the erasure period
declared for it.

```console
  acme.fraud/transactions-scored-daily
    purpose       fraud-detection
    legal basis   legitimate-interest
    categories    financial, behavioural
    subjects      customer
    residency     eu
    retention     7y
    unclassified  1 of 3 datasets carry no classification: wh/vendor_feed
```

Three rules make that reportable rather than guessed:

- **Nothing is inferred from a column name.** A column called `email` is not evidence
  of anything; a category is reported only where something declared it.
- **A classification is never carried from one dataset to another.** What an activity
  wrote is the controller's declaration about its own output. The table it read belongs
  to somebody else, and asserting a category for it would invent evidence.
- **Unclassified is counted and named.** A dataset nobody classified is *nobody said*,
  never *no personal data* — the same distinction `quality` keeps between *not checked*
  and *passed*.

A value outside a closed term is reported and withholds the mark, which is how
`special_category` works: Art. 9(1) lists exactly eight kinds of data, and an invented
ninth reaching a record is a defect that looks like data. A *missing* classification
does not withhold the mark, because that would fire on nearly every run and a mark
that is always withheld says nothing.

**No OpenLineage integration emits that facet yet**, although the spec has carried it
since `1-0-0` and both clients generate it. `pipeline-runtime` emits it from the LF-tags
it resolves, and anything else that can attach a dataset facet can too.

### What only a person can say

Two of the seven Art. 30(1) items are not in any event and never will be: (d) the
categories of recipients, and (g) the security measures. A recipient is who receives
data outside the platform, and a security measure is an arrangement rather than
something that runs. Both can be asserted, in the mapping file for a job that emits
lineage or in the declared-activities document for one that does not:

```yaml
jobs:
  "acme.fraud/transactions-*":
    recipients:
      - the group's fraud bureau
      - the card scheme, for disputed transactions
    security_measures:
      - pseudonymised card numbers at rest
```

Every format marks them `declared`, because there is no evidenced case to tell them
apart from and an unmarked value would read like the columns beside it. **Asserting
them does not withhold the mark**: there is no evidence to fall short of, and
withholding would punish a controller for filling the field in.

The scope statement says the same thing once, for the record as a whole: it has a field
for all seven items, and *(d) and (g) can only be declared*.

### Declared activities

Processing that emits no lineage — a payroll SaaS, staff using a vendor's assistant,
anything on paper — can be written into a separate document and passed with
`--activities`:

```console
$ qedro ropa demo/lineage-declared --config demo/qedro.yaml --activities demo/activities.yaml
  payroll-run  (hr)  — declared, no lineage
    purpose       payroll (declared)
    legal basis   legal-obligation (declared)
    reads         no lineage — declared: employee master data, working time records
    writes        no lineage
    runs          no lineage
```

Every field of a declared activity is an assertion, since nothing in the events shows
the processing happened. Where the events would have supplied a value, the output
says `no lineage` rather than leaving a blank or printing `0`: a blank reads as
*touches no data*, and `0` as *ran zero times*, and neither is known. Declared
activities are counted on their own line in the scope statement and leave the
evidenced counts unchanged. Any declared activity withholds the mark. The reasoning
behind each of those choices is recorded on
[#6](https://github.com/cordata-tech/qedro/issues/6).

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

A job's domain is guessed from the last segment of its namespace, so `acme.fraud` is in
`fraud`, unless a rule sets `domain:`. The guess fails for an integration that names its
namespace after itself: openlineage-dbt defaults to `dbt`, which puts every model in a
domain called `dbt` and makes a declared `orders` look silent. When `domains:` is set,
the scope statement says which domains were guessed and which came from a rule, and
the silent-domain reason names the guess, so a wrong guess can be told apart from a
domain that emitted nothing:

```yaml
jobs:
  "dbt/*orders*":
    domain: orders
```

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
    model version            2026-07-fraud-v3    7 runs, 2026-07-20 to 2026-07-26
                             2026-06-fraud-v2   14 runs, 2026-07-06 to 2026-07-19
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

- **Art. 26 is context, not a finding.** The inputs a run read are printed as context
  for Art. 26(4), not as a check that input data is relevant and sufficiently
  representative, which the view cannot make. The span of run records is printed as
  context for Art. 26(6), not as a retention policy.
- **Art. 26 is cited with its condition.** The deployer duties apply to high-risk
  systems listed in Annex III from 2 December 2027, cited from the consolidated text
  (CELEX 02024R1689-20260727). Nothing in the events says whether a system is
  high-risk, so the view does not decide it.
- **Retention is the span of run records in view**, not a retention policy, which the
  events do not carry. Art. 26(6) sets a minimum period for logs, and GDPR storage
  limitation pulls the other way for personal data, so the view reports the span and
  resolves neither. A short span does not withhold the mark, because withholding it
  would imply Art. 26(6) applies today.
- **Declared use cases are marked as declared.** Most AI use outside engineering teams
  emits no lineage, for example staff pasting text into a vendor's assistant.
  The view takes declared activities from the Art. 30 record and lists the ones that
  name a `model`; each is shown as `declared, no lineage` and withholds the mark. A
  declared activity with no model, such as a payroll SaaS, stays in the Art. 30
  record and is not an AI use case.

The model version is read from two documented places: the standard OpenLineage `tags`
run facet with key `model_version`, and `step_params.<step>.model_version` in the
`cordata_provenance` facet that `pipeline-runtime` emits. An activity whose runs report
neither is counted in the scope statement and not listed.

## What changed between two records

`qedro diff` compares two JSON records with no database between them — a before and
an after a team keeps in Git. It reports the thing neither document shows on its own:

```console
$ qedro ropa ./lineage --format json --out records/2026-06.json
$ qedro ropa ./lineage --format json --out records/2026-09.json
$ qedro diff records/2026-06.json records/2026-09.json

  acme.fraud/transactions-scored-daily
    purpose       fraud-detection, unchanged
                  evidence lost: emitted facet → mapping file
```

The purpose is the same string in both records, and the claim behind it is not. A
pipeline that stopped emitting its facet still produces a record that reads
correctly; what it stopped producing is the evidence, and only a comparison can say
so. The same applies to a cloud migration: the before-and-after legal asks for is two
records, not a database.

**A diff prints no mark.** ∎ means *this artefact stands on its own evidence*, and a
comparison's evidence is two documents it cannot verify — so it reports each record's
own verdict and none of its own. It also says first whether the two records cover the
same source and window, because a difference in coverage otherwise reads as a
difference in processing.

## The assertion history

`qedro quality` reports what was actually checked about each dataset, and when — and
it gives equal weight to what was not:

```console
$ qedro quality demo/lineage --config demo/qedro.yaml
  warehouse/fraud_curated.transactions_scored  (fraud)
    asserted by   acme.fraud/scores-validated
    runs          20 in window, last 2026-07-26T02:51:00+00:00
    expectations  5 — 4 held, 1 failed
      held    expect_column_values_to_be_unique on tx_id           20 runs
      FAILED  expect_table_row_count_to_be_between                 20 runs, 2 failed, last 2026-07-15

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
The scope statement names the filter and says how many datasets it left out and in
which domains, because a dataset's domain is often guessed from the job namespace, and
a dataset left out by a wrong guess would otherwise look like one that does not exist:

```console
    filter        --domain orders left out 4 datasets: 4 in dbt (guessed from the job
                  namespace)
```

A filter that leaves some datasets out does not withhold the mark. One that leaves out
every dataset says so, instead of reporting that nothing was found.

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

It is not decoration. [Art. 5(2) GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
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

## What this is not

**It is not legal advice, and it does not decide compliance.** It reports what the
events say and where each value came from. Whether the resulting record satisfies an
obligation is a judgement for whoever is accountable for it — a data protection officer,
legal counsel, a supervisory authority — and the artefact is written to support that
judgement rather than to stand in for it. Where an article is named in the output, it
says which field the record holds, never that the article is satisfied.

**The record is the controller's, not the tool's.** Art. 30 puts the duty on the
controller, and a generated record is a draft until somebody with that responsibility
reviews and signs it. The tombstone means *this artefact stands on its own evidence*,
which is a statement about provenance, not an approval.

**It covers the processing that emits lineage.** Every record says so, and says which
Art. 30(1) items it has fields for — today (a) the controller and (b) the purposes.
Anything that emits no lineage appears only if it is declared, and a declared activity
is an assertion rather than evidence.

**It is early software.** `0.x` interfaces move between releases, the changelog says
which, and [Apache-2.0](LICENSE) carries no warranty.

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
