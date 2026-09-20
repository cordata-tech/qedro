# Transcript: `qedro diff` against a hand-maintained register

Captured by script from qedro 0.3.0, at commit `aea509e` with a clean working tree,
on Python 3.12.13. The output below is what the command printed, unedited. Run the same
commands from the repository root to reproduce it.

`demo/register.yaml` is an AI register of four rows, maintained by a separate
governance workstream eighteen months ago. `demo/lineage-declared` is three weeks of
lineage from pipelines that declare their purpose and lawful basis. Neither document
knows about the other, which is the situation
[platform#48](https://github.com/cordata-tech/platform/issues/48) describes.

**Four rows, four outcomes.** One is still true and reports nothing. One names a
purpose the pipeline stopped having. One describes a pipeline that no longer exists.
One names a model version in production that no run has ever reported — which is the
claim refusal (b) rests on, and the only one of the four that a parallel register
cannot fix by being more diligent, because nothing in the platform emits it.

Note what the comparison does **not** do. It prints no mark: ∎ means *this artefact
stands on its own evidence*, and a comparison's evidence is two documents it cannot
verify. It reports each document's own verdict instead, and a register has none —
which the output says rather than leaving blank.

## 1. The record the register is checked against

```console
$ qedro ropa demo/lineage-declared --config demo/qedro.yaml --format json --out record.json
  wrote record.json  ∎
```

## 2. Where the register and the record disagree

```console
$ qedro diff demo/register.yaml record.json
Where the register and the record disagree

  ! a register covers whatever its owners wrote down, and the record covers
  demo/lineage-declared over the window below — so an entry on one side only may be a
  gap in either, and the record's window is what decides which
  ! the register names a model for one or more entries, and the Art. 30 record has no
  field for one — compare against `--view deployer`, which reports the model version
  each run declared, before treating these as drift

  acme.billing/dunning-legacy  — dunning-legacy, Billing, unassigned since 2025-11
    removed       in the register and not in the record
                  no pipeline emitted it in the window

  acme.billing/dunning-weekly  — not in the register
    added         in the record and not in the register
                  nobody wrote this one down

  acme.billing/invoices-nightly  — not in the register
    added         in the record and not in the register
                  nobody wrote this one down

  acme.crm/consent-sync  — churn-prediction, Data Science, M. Lindqvist
    legal basis   register: legitimate-interest · record: legal-obligation
                  the register contradicts the evidence
    model         register: churn-v4 · record: nothing
                  the register claims something the record cannot see
    purpose       register: churn-prediction · record: consent-management
                  the register contradicts the evidence
    reads         record: warehouse/crm_raw.consent_events
                  the register does not list it
    reads         register: warehouse/crm_curated.customers
                  the record does not report it

  acme.crm/customers-curated  — crm-enrichment, Customer Platform, S. Okafor
    legal basis   register: consent · record: contract
                  the register contradicts the evidence
    purpose       register: marketing · record: customer-administration
                  the register contradicts the evidence
    reads         record: warehouse/crm_raw.accounts
                  the register does not list it
    reads         record: warehouse/crm_raw.contacts
                  the register does not list it
    reads         register: warehouse/crm_raw.customers
                  the record does not report it

  acme.fraud/scores-validated  — not in the register
    added         in the record and not in the register
                  nobody wrote this one down

  14 findings across 6 entries; 1 in the register only, 3 in the record only; 1 agree throughout

  Scope of this comparison
    source        demo/register.yaml against record.json
    window        2026-07-06T01:30:00+00:00 to 2026-07-26T04:06:00+00:00
    register      demo/register.yaml — 4 entries
    record        record.json — 2026-07-06T01:30:00+00:00 to 2026-07-26T04:06:00+00:00
    read from     demo/lineage-declared
    This comparison covers the entries in the register and the activities in the record.
    It verifies neither: a register is what its owners wrote down, and the record covers
    only pipelines that emitted lineage within its window — so an entry on one side and
    not the other is a question rather than an answer.

  The documents' own verdicts
    register      a hand-maintained document; it makes no claim
    record        stands on its own evidence
```

Exit status 0. The cautions above also go to standard error, so a run whose output was redirected to a file still shows them.
