# Comparing records and signing them off

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

### Or a register against the record

Hand one side a register instead of a record and the same command reports where the
two disagree — which is the AI governance programme's spreadsheet checked against what
the pipelines actually did:

```console
$ qedro diff demo/register.yaml record.json

  acme.crm/customers-curated  — crm-enrichment, Customer Platform, S. Okafor
    purpose       register: marketing · record: customer-administration
                  the register contradicts the evidence
```

Which side rests on evidence is the finding. A register contradicting an emitted facet
means the register is wrong or the pipeline is doing something nobody wrote down; two
hand-maintained documents disagreeing means somebody has to decide; and a register
naming a model no run ever reported is a claim nothing can check. Every finding carries
the owner of the register row, because a report whose reader has to go and ask around
for that has done half the job.

A field the register does not carry is not a disagreement — a register is a partial
document by nature, and reporting everything it omits would bury the findings that
matter. See [`docs/evidence/register-drift.md`](evidence/register-drift.md) for
the whole thing, captured from a real run.

## Signing a record off

A record of processing activities is the controller's document, and a person signs it.
`qedro sign` keeps who accepted which version, and when, in a file beside the record's
JSON:

```console
$ qedro ropa ./lineage --out record.json
$ qedro sign record.json --as "Max Mustermann" --state "for sign-off"
  record.json: waiting for sign-off, requested by Max Mustermann on 2026-11-17
$ qedro sign record.json --as "Erika Mustermann" --state approved --note "reviewed with the data team"
  record.json: approved by Erika Mustermann on 2026-11-17, prepared by Max Mustermann on 2026-11-17 — reviewed with the data team
$ qedro status .
  record.json  ropa        mark earned    approved by Erika Mustermann on 2026-11-17, prepared by Max Mustermann on 2026-11-17 — reviewed with the data team
```

The states are *draft*, *for sign-off*, *approved* and *published*, one step forward at
a time or back to draft, and `record.signoff.json` is only ever added to. Each entry
names the SHA-256 of what the record *states*: the controller, each activity's purpose,
legal basis, categories, recipients and the datasets it reads and writes, and the
verdict with its reasons. Run counts, timestamps, the window, the qedro version and
display fields are left out, so a record rebuilt tomorrow over new runs of the same
pipelines, or by a newer qedro, is still covered, while one that states anything
different is not: `qedro status` then reports it as not signed off, naming the earlier
sign-off. The covered fields are an explicit list per projection with a version, which
each entry records, so an upgrade never reopens an approval by accident. Kept in Git,
the file's history is the audit trail.

`--signoff record.signoff.json` on any projection prints where the record it builds
stands, under the verdict, in every format. **A sign-off is a person's acceptance of
the record, not evidence:** it never earns or withholds the mark, and every format says
so beside it.

### Four eyes: a second person approves

The person who sends a version for sign-off is its preparer, and `qedro sign --state
approved` refuses when the approver's name is the preparer's, in a sentence naming
both. Names are compared ignoring case and spacing. Every format prints both names
beside the verdict, and the JSON carries `prepared_by`, `approved_by` and
`second_person`. A team where one person does both says so once, where the records
live:

```yaml
# qedro.yaml
signoff:
  four_eyes: false
```

The approval then stands and says *with no second person: Erika Mustermann also
prepared it*, and `qedro status` counts such approvals, in its text and as
`approved_without_second_person` in its JSON. Approvals made before 0.25 are read the
same way, so one where a single person did both is counted rather than hidden.

What this can prove is limited by where the names come from. `--as` is whatever the
person running the command types, so four eyes here catches a mistake — the preparer
approving their own record out of habit — and does not stop someone typing a
colleague's name. The signed Git commit that added an entry identifies its signer by
key, and an identity provider would identify them by login; either could stand behind
these names later, and which one is a question for
[#19](https://github.com/cordata-tech/qedro/issues/19). Until then the sign-off file's
Git history, with signed commits, is the stronger record of who did what.

### Whether a signed record still describes what runs

A signed record describes the pipelines on the day it was signed. `qedro status
--against` builds a fresh record from the lineage, as `qedro ropa` would, and compares
every signed Art. 30 record with it, one activity at a time
([#42](https://github.com/cordata-tech/qedro/issues/42)):

```console
$ qedro status records --against ./lineage --config qedro.yaml
  fraud.json  approved by Max Muster on 2026-11-19
    stale       acme.billing/dunning-weekly
                  purpose: debt-collection, unchanged — evidence lost: emitted facet → mapping file
    new         payroll-run
    up to date  acme.billing/invoices-nightly, acme.crm/consent-sync, …

  1 signed record: 6 up to date, 1 stale, 1 new, 0 blocked
```

*Stale* means something the record states has changed since it was signed, and names
it, including a value that is the same string resting on weaker evidence. *New* is an
activity the fresh run has and the signed record does not. A job that only ran again
is up to date: the comparison is `qedro diff`'s, over what a record states, never its
run counts or timestamps. *Blocked* means no comparison could be made, and the reason
is always printed: a fresh run that read no events blocks every signed record rather
than reading as a platform where every job stopped. A fresh run over a different source
or window says so above its findings, since an activity missing from one may never
have been in it.

`--regenerate --as NAME` turns the stale and new activities into a version to review
([#55](https://github.com/cordata-tech/qedro/issues/55)): for each signed record that
changed, it writes the fresh record beside it as `record.next.json` and adds a *for
sign-off* entry for that version, by NAME, naming what changed. The signed record and
its entries are left exactly as they were. `record.next.json` shares the record's
sign-off file, so `qedro sign record.next.json --state approved` adds to the same
history, and replacing `record.json` with it afterwards keeps the approval:

```console
$ qedro status records --against ./lineage --config qedro.yaml --regenerate --as "Laszlo"
  ...
    wrote fraud.next.json, sent for sign-off by Laszlo
$ qedro sign records/fraud.next.json --as "Erika Mustermann" --state approved
```

`--format json --out records/status.json` writes the same as a document: each record,
its verdict and sign-off, and with `--against` each activity's state and what changed,
in the words the text uses, for a reader such as a console that shows which signed
records have gone stale.
