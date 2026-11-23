# The Art. 30 record

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

## Orchestration parents are not activities

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

## Jobs that process no personal data

A platform that also runs pipelines over data about no person — fund prices, sensor
readings, exchange rates — would otherwise list each of those jobs as an activity with
no purpose and no legal basis, and withhold the mark for gaps that are not gaps. A rule
in the mapping file can leave such jobs out, with the reason in the rule's own words:

```yaml
jobs:
  "acme.funds/*":
    out_of_scope: fund prices and figures, no personal data
```

The jobs it matches are left out of the activities and named in the scope statement
with that reason, so the record says what it left out and why rather than leaving it
out silently. They still count among the jobs in view, and a domain whose only jobs were
left out is seen rather than silent:

```console
    left out      5 jobs not listed as activities, by a rule in the mapping file saying
                  fund prices and figures, no personal data: acme.funds/fund_check,
                  acme.funds/fund_figures, acme.funds/fund_kid, acme.funds/fund_prices,
                  acme.funds/fund_share_classes
```

The rule is a statement by whoever wrote the mapping file, so qedro checks it against
what the datasets carry. If a left-out job reads or writes a dataset with a
classification answering Art. 30(1)(c) — the categories of data subjects and of
personal data — the mark is withheld, and the reason names the job and each dataset
with its classification. A value the vocabulary flags `personal: false` is no
contradiction; the shipped vocabulary flags `subject_type: none`, so a table tagged as
holding no personal data agrees with the rule. A rule cannot also give a purpose, a
legal basis, recipients or security measures, since those describe the job as an
activity of the record. In the JSON, `scope.left_out` lists each job with its reason,
its rule and any `personal_data` findings, beside the fields a sign-off covers.

## What the data is

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

## What only a person can say

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

## Declared activities

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

## Where each value came from

Every field of an Art. 30 record can say where its value came from in a sentence, built
only from what the record holds, and which requirement of the regulation the field
answers ([#48](https://github.com/cordata-tech/qedro/issues/48)):

```console
$ qedro ropa demo/lineage --config demo/qedro.yaml --explain
  ...
Where each value came from

  ...
  acme.fraud/transactions-scored-daily
    Purpose: fraud-detection
      Asserted in demo/qedro.yaml (line 37), rule acme.fraud/transactions-*, because acme.fraud/transactions-scored-daily emitted no purpose in a processing facet. (Art. 30(1)(b) GDPR)
```

An explanation names the run whose event carried a value, or the mapping rule and its
line, or the declaration, and never judges whether the value is the right one. Text
and Markdown add them with `--explain`, to stay readable without. JSON carries them
under `explain`, the PDF as footnotes under each activity, and the workbook on an
Explanations sheet; all three quote the regulation's wording once. The requirements
are a document, `regulations/gdpr.yaml`, loaded at runtime like the vocabulary, and
`references:` in qedro.yaml points at another one.

## Output

`--format text|markdown|json|xlsx|pdf`, and `--out` to write a file. The format follows
the filename when you do not say — `--out ropa.xlsx` is a workbook, `--out ropa.md`
is markdown — and an explicit `--format` always wins.

**xlsx is the one an auditor asks for**, and it is the only output that has to
survive being forwarded. Two sheets: the activities, and the scope. The verdict
sits above the table on the first sheet rather than behind it, because a caveat
below the data is a caveat nobody reads — the same failure this tool exists to
prevent, reproduced in its own output. Where a value came from is a column of
words; the tint on a cell is reinforcement and never carries the meaning alone.

**PDF is the version somebody files, prints and signs**, so far for the Art. 30
record, the erasure record and the provenance chain: `qedro ropa … --out record.pdf`,
after `pipx install 'qedro[pdf]'`. The verdict comes first. The Art. 30 record then
lists its activities, and gives each one a table of the Art. 30(1) items with where
every value came from. The erasure record and the provenance chain draw a tree with
each box's state written in it — everything descended from the erased dataset, or
every step back from the published one with its commit and whether that commit was
signed — and a table of the same rows. Each ends with the scope statement, and the
same events give the same bytes. The deployer view and the quality history refuse
`--out *.pdf` with a sentence until their PDFs exist (#37).

## Configuration

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

platforms:          # labels for the platform line, merged over qedro's own
  s3: the export bucket
  cordata:          # a namespace scheme qedro does not know, with the kind
    label: AWS Glue # that picks its icon in a PDF tree
    kind: database
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

## The vocabulary is a document, not an enum

The six Art. 6(1) bases live in a YAML file the tool loads at runtime, not in Python.
Point `--vocabulary` at your own and the shipped one is replaced wholesale — which is
what makes an organisation's own ontology possible later without a rewrite. A value
outside a closed term is flagged and still reported; refusing to read what an emitter
actually sent would hide the finding that matters.

A value can carry `personal: false` to say it describes data about no person, as the
shipped `subject_type: none` does. It is the only way qedro learns that, and it matters
in one place: a job left out as processing no personal data may touch a dataset
classified with such a value without contradicting the rule. A vocabulary of your own
flags its own values; a value it does not flag counts as personal.

## The deployer view

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
