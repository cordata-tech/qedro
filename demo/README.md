# The demo estate

Three weeks of OpenLineage from a company that does not exist. Everything here
is synthetic and committed, so `qedro` can be run against something real-shaped
without anyone needing a warehouse, an account, or a client's data.

**ACME Finanz GmbH** runs six pipelines across three domains, emitted by dbt,
Airflow and Spark. There is no Cordata infrastructure anywhere in it — no
LakeFormation, no AWS, no descriptor model. That is the point: the tool has to
work against what people already run, and a demo that quietly needed our own
stack would prove the opposite.

```
demo/
  qedro.yaml           the controller, the domains, and a mapping fallback
  activities.yaml      one declared use of an AI assistant that emits no lineage
  lineage/             the estate as it is today — no Art. 30 facet anywhere
  lineage-declared/    the same three weeks once the pipelines declare
```

The two estates are **identical** — same jobs, same datasets, same runs, same
run IDs. The only difference is whether each job carries the `processing` facet.
That is what makes the comparison below mean something.

## Three runs, and the difference between them

### 1. Lineage alone

```console
$ qedro ropa demo/lineage
```

Six activities, every one of them with no purpose and no lawful basis. Lineage
says *what happened*; Art. 30(1)(b) asks *why*, and no graph of jobs and datasets
contains that. The mark is withheld, and the reasons say so:

```
  this record does not claim to be a proof:
    ! no controller is declared, and Art. 30(1)(a) requires one — set `controller:` in qedro.yaml
    ! 6 of 6 activities have no purpose or no legal basis from any source
```

### 2. Lineage plus the mapping file

```console
$ qedro ropa demo/lineage --config demo/qedro.yaml
```

Now the record is populated and readable — and every filled-in value is labelled
`(mapping)`, because it came from a file somebody typed rather than from the
pipeline that ran:

```
  acme.fraud/transactions-scored-daily
    purpose       fraud-detection (mapping)
    legal basis   legitimate-interest (mapping)
```

Still no mark, for two reasons — and the second is the interesting one:

```
    ! 5 of 6 activities rely on the mapping file rather than on an emitted facet, so those entries are asserted rather than proven
    ! 1 of 6 activities has no purpose or no legal basis from any source
```

**That one activity is `acme.crm/consent-sync`.** It matches none of the patterns
in `qedro.yaml`, because it was added to the platform after the file was written
and nobody went back to it. Nothing in the estate is broken and nothing failed —
the register simply drifted, silently, the way every hand-maintained register
does. The difference is that here it is a line in the output rather than an
absence nobody noticed.

### 3. Lineage that declares

```console
$ qedro ropa demo/lineage-declared --config demo/qedro.yaml
```

```
  provenance    6 evidenced, 0 from the mapping file, 0 undeclared

  every activity stands on emitted evidence   ∎
```

The mapping file is still there and is now unused: a facet always beats it. Every
purpose and every lawful basis came from the job that ran, in the same event that
proves it ran — so the record stands on its own evidence, and the run finishes the
product's name.

## The deployer view, on the same record

```console
$ qedro ropa demo/lineage-declared --config demo/qedro.yaml --view deployer
```

One of the six activities reported a model version: the fraud scoring job, whose runs
carry a `model_version` entry in the standard OpenLineage `tags` run facet. The model
changed on 15 June, so the view lists `2026-05-fraud-v2` for 14 runs and
`2026-06-fraud-v3` for the last 7, and names the inputs the latest run read. Purpose
and legal basis are the Art. 30 record's own entries, so in `lineage-declared` they
come from the emitted facet and the view earns the mark, while in `lineage` they come
from the mapping file and it does not. The `tags` facet is identical in both
directories, which still differ only in the `processing` facet.

The span of run records is 20 days, and the view says so without calling it a
retention period, since nothing in the events states one.

```console
$ qedro ropa demo/lineage-declared --config demo/qedro.yaml --view deployer \
    --activities demo/activities.yaml
```

`activities.yaml` declares one use that emits no lineage: support staff drafting
replies by pasting ticket text into a vendor's assistant. It appears as
`support-reply-drafts — declared, no lineage`, every field is marked as declared, and
the view no longer claims to be a proof, because nothing in the events shows that use
happened, which model it used, or what it read.

## The assertion history, on the same estate

```console
$ qedro quality demo/lineage --config demo/qedro.yaml
```

Two datasets carry assertions and ten do not. `scores-validated` checks five
expectations on `fraud_curated.transactions_scored` every night, and the row-count
expectation failed twice — on the 6th and the 10th, when scoring volume dropped.
`dunning-weekly` checks three expectations on `billing_curated.invoices`, on its own
weekly cadence, and asserted twice rather than three times because one Monday's run
failed before it got there.

The other ten datasets appear under **Not checked**, and that is the point of the
projection: nothing failed on them because nothing ran on them.

Note what does *not* withhold the mark here — the failing expectation. The mark says
the history is complete, not that the data is good.

## The provenance chain, on the same estate

```console
$ qedro provenance demo/lineage --dataset billing_curated.dunning_cases
```

Three hops back to the source tables, and it crosses a domain boundary on the way:
billing's invoices are built from crm's customers. Every produced step names a
repository, a commit, a branch and a file — the estate emits `sourceCodeLocation`,
because dbt, Airflow and Spark all do.

**And not one step can show a signature**, so the chain does not claim to be a proof.
That is not a gap in the demo. Nothing standard in OpenLineage reports whether a
commit was signed, and the estate is deliberately built from what people already run.
`pipeline-runtime` does report it, which is what the third tier of the adoption story
looks like here.

The three source tables at the end are marked as endings rather than failures — and
the reasons say what an ending means, since a source dataset and a producing run
outside the window are indistinguishable from here.

## Worth noticing

**The scope statement is on all three**, including the one that earns the mark.
It says what was looked at and what could never have been looked at. A record
covering pipelines is a complete record of the pipeline-borne subset and never of
everything a controller does, and printing that only when coverage was poor would
teach a reader that its absence means full coverage.

**Two runs failed** — one `scores-validated`, one `dunning-weekly`. Three weeks of
production lineage with nothing failing in it is not production lineage. They are
visible in `qedro events demo/lineage` as `fail 2`, they do not affect the Art. 30
record because a failed run is still processing that happened, and they are why the
weekly job asserted twice rather than three times.

**The events carry facets nothing here reads** — `sql`, `jobType`, `nominalTime`,
`dataSource`, `errorMessage`. They are in the estate because real events carry
them, and they arrive intact through a reader that models none of them. That is
the shallow-model rule working rather than being asserted.

**The assertions are an *input* facet**, which is where Great Expectations and dbt
put them, and it is the reason the history can speak in dates. *This table has a
unique key* is a claim about the table; *the run on the 10th checked it and it held*
is evidence about a run.

## Regenerating

```console
$ python tools/seed.py
```

Deterministic: no clock, no randomness, run IDs are UUIDv5 over the job and the
day. Two runs produce byte-identical files, so a diff in this directory is always
a real change to the estate. CI runs `python tools/seed.py --check` so the
committed events and the generator cannot drift apart.
