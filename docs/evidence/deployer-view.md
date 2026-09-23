# Transcript: `qedro ropa --view deployer`

Captured by script from qedro 0.4.0, at commit `85ef563` with a clean working tree,
on Python 3.12.13. The output below is what the command printed, unedited. Run the same
commands from the repository root to reproduce it.

The three runs use the same config and differ in one thing each. The first reads
`demo/lineage`, where purpose and legal basis come from the mapping file. The second
reads `demo/lineage-declared`, where the pipelines emit them. The third adds
`demo/activities.yaml`, which declares two uses that emit no lineage: a support
assistant, which names a model and is listed, and a payroll SaaS, which names none and
belongs only in the Art. 30 record.

## 1. Lineage whose pipelines do not declare, with purpose and basis from the mapping file

```console
$ qedro ropa demo/lineage --config demo/qedro.yaml --view deployer
AI use cases, deployer view of the Art. 30 record — ACME Finanz GmbH

  Regulation (EU) 2024/1689 (AI Act), consolidated text CELEX 02024R1689-20260727.
  Art. 26 applies from 2 December 2027 to deployers of Annex III high-risk systems.
  Whether any use case here is high-risk is not decided by this view.
  Purpose and legal basis are the Art. 30 record's own entries, not restated.

  acme.fraud/transactions-scored-daily  (fraud)
    purpose                  fraud-detection (mapping)
    legal basis              legitimate-interest (mapping)
    model version            2026-07-fraud-v3    7 runs, 2026-07-20 to 2026-07-26
                             2026-06-fraud-v2   14 runs, 2026-07-06 to 2026-07-19
                             reported in the tags run facet
    latest run               2026-07-26T02:21:00+00:00, model 2026-07-fraud-v3
                             run 78766c96-379c-5818-adc6-96c2f8f9e7d3
    inputs read              warehouse/fraud_raw.device_events,
                             warehouse/fraud_raw.transactions
                             context for Art. 26(4), not a check of relevance or
                             representativeness
    run records              21 runs, 2026-07-06 to 2026-07-26 (20 days) — less than six
                             months in view
                             context for Art. 26(6), not a retention policy or a
                             compliance finding

  Scope of this view
    source        demo/lineage
    window        2026-07-06T01:30:00+00:00 to 2026-07-26T04:06:00+00:00
    in view       1 of 7 activities reported a model version, 0 declared, 218 events
    runs          21 runs of the listed use cases
    This view lists the activities in the Art. 30 record whose runs reported a model
    version, and use cases declared with no lineage. An AI use that emits no lineage and
    is not declared is not represented here. The retention shown is the span of run
    records in view, not the source's retention policy, which the events do not carry.
    Art. 26(6) sets a minimum period for logs under a deployer's control while GDPR
    Art. 5(1)(e) storage limitation pulls the other way for personal data, and this view
    resolves neither.

  this view does not claim to be a proof:
    ! 1 of 1 use case takes purpose or legal basis from the mapping file rather than an emitted facet, so that entry is asserted
```

Exit status 0.

## 2. The same three weeks once the pipelines declare

```console
$ qedro ropa demo/lineage-declared --config demo/qedro.yaml --view deployer
AI use cases, deployer view of the Art. 30 record — ACME Finanz GmbH

  Regulation (EU) 2024/1689 (AI Act), consolidated text CELEX 02024R1689-20260727.
  Art. 26 applies from 2 December 2027 to deployers of Annex III high-risk systems.
  Whether any use case here is high-risk is not decided by this view.
  Purpose and legal basis are the Art. 30 record's own entries, not restated.

  acme.fraud/transactions-scored-daily  (fraud)
    purpose                  fraud-detection
    legal basis              legitimate-interest
    model version            2026-07-fraud-v3    7 runs, 2026-07-20 to 2026-07-26
                             2026-06-fraud-v2   14 runs, 2026-07-06 to 2026-07-19
                             reported in the tags run facet
    latest run               2026-07-26T02:21:00+00:00, model 2026-07-fraud-v3
                             run 78766c96-379c-5818-adc6-96c2f8f9e7d3
    inputs read              warehouse/fraud_raw.device_events,
                             warehouse/fraud_raw.transactions
                             context for Art. 26(4), not a check of relevance or
                             representativeness
    run records              21 runs, 2026-07-06 to 2026-07-26 (20 days) — less than six
                             months in view
                             context for Art. 26(6), not a retention policy or a
                             compliance finding

  Scope of this view
    source        demo/lineage-declared
    window        2026-07-06T01:30:00+00:00 to 2026-07-26T04:06:00+00:00
    in view       1 of 7 activities reported a model version, 0 declared, 218 events
    runs          21 runs of the listed use cases
    This view lists the activities in the Art. 30 record whose runs reported a model
    version, and use cases declared with no lineage. An AI use that emits no lineage and
    is not declared is not represented here. The retention shown is the span of run
    records in view, not the source's retention policy, which the events do not carry.
    Art. 26(6) sets a minimum period for logs under a deployer's control while GDPR
    Art. 5(1)(e) storage limitation pulls the other way for personal data, and this view
    resolves neither.

  every AI use case in view stands on emitted evidence   ∎
```

Exit status 0.

## 3. The same record with declared activities that emit no lineage

```console
$ qedro ropa demo/lineage-declared --config demo/qedro.yaml --view deployer --activities demo/activities.yaml
AI use cases, deployer view of the Art. 30 record — ACME Finanz GmbH

  Regulation (EU) 2024/1689 (AI Act), consolidated text CELEX 02024R1689-20260727.
  Art. 26 applies from 2 December 2027 to deployers of Annex III high-risk systems.
  Whether any use case here is high-risk is not decided by this view.
  Purpose and legal basis are the Art. 30 record's own entries, not restated.

  acme.fraud/transactions-scored-daily  (fraud)
    purpose                  fraud-detection
    legal basis              legitimate-interest
    model version            2026-07-fraud-v3    7 runs, 2026-07-20 to 2026-07-26
                             2026-06-fraud-v2   14 runs, 2026-07-06 to 2026-07-19
                             reported in the tags run facet
    latest run               2026-07-26T02:21:00+00:00, model 2026-07-fraud-v3
                             run 78766c96-379c-5818-adc6-96c2f8f9e7d3
    inputs read              warehouse/fraud_raw.device_events,
                             warehouse/fraud_raw.transactions
                             context for Art. 26(4), not a check of relevance or
                             representativeness
    run records              21 runs, 2026-07-06 to 2026-07-26 (20 days) — less than six
                             months in view
                             context for Art. 26(6), not a retention policy or a
                             compliance finding

  support-reply-drafts  (crm)  — declared, no lineage
    purpose                  customer-support (declared)
    legal basis              contract (declared)
    model                    the support desk vendor's built-in assistant; version not
                             visible to ACME (declared)
    inputs read              customer emails, support ticket history (declared)
                             context for Art. 26(4), not a check of relevance or
                             representativeness
    run records              none — nothing emits lineage for this use
                             context for Art. 26(6), not a retention policy or a
                             compliance finding
    note                     Support staff draft replies by pasting ticket text into the
                             vendor's UI. Nothing in the data platform emits lineage for
                             this.

  Scope of this view
    source        demo/lineage-declared
    window        2026-07-06T01:30:00+00:00 to 2026-07-26T04:06:00+00:00
    in view       1 of 7 activities reported a model version, 1 declared, 218 events
    runs          21 runs of the listed use cases
    This view lists the activities in the Art. 30 record whose runs reported a model
    version, and use cases declared with no lineage. An AI use that emits no lineage and
    is not declared is not represented here. The retention shown is the span of run
    records in view, not the source's retention policy, which the events do not carry.
    Art. 26(6) sets a minimum period for logs under a deployer's control while GDPR
    Art. 5(1)(e) storage limitation pulls the other way for personal data, and this view
    resolves neither.

  this view does not claim to be a proof:
    ! 1 use case is declared rather than evidenced — no run records exist for it, so nothing shows that it happened, which model was used or what was read
```

Exit status 0.
