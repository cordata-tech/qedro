# The assertion history

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
