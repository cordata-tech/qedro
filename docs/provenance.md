# The provenance chain

`qedro provenance` answers the question a published number provokes — where did this
come from, and who authorised it? It walks backwards: the run that produced the
dataset, the code that run executed, the commit it was at, and then the same for
everything that run read.

```console
$ qedro provenance demo/lineage --dataset billing_curated.dunning_cases
  warehouse/billing_curated.dunning_cases
    produced by   acme.billing/dunning-weekly
    platform      dbt · PostgreSQL
    code          https://github.com/acme-finanz/data-platform at b7eb23bd289c
                  main models/billing/dunning_cases.sql
    signature     signature unknown — nothing reported it
    source        publisher unknown — nothing reported it

    warehouse/billing_curated.invoices
      produced by   acme.billing/invoices-nightly
      ...

      warehouse/crm_raw.accounts
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

**The `source` line is one hop further out than the commit.** A published number
usually depends on data somebody else's application wrote, and where the events say
so, the step names the application release behind what the run read rather than only
the commit behind the pipeline. Unknown there is counted in the scope statement and
does not withhold the mark: the chain claims authorisation, and a missing publisher
says nothing about that. There is no standard facet for it — `datasetVersion` says
which version a run read without saying who published it — so today only
`pipeline-runtime` reports it.

**The `platform` line says what ran the step and where its output lives**, as the
events say: the integration from the standard `jobType` facet, or from the `producer`
URL, and the platform from the dataset's namespace (`snowflake://…`, `s3://…`) or its
`dataSource` facet. Nothing is guessed from a name, so where the events say neither
the line reads *not reported*. A namespace written as a URI is not always a platform
— pipeline-runtime's `cordata://fraud` names a domain — so a scheme qedro has no label
for is left out rather than printed; `platforms:` in `qedro.yaml` gives it one.

**The `checks` line says what was checked on each input as the step read it**: the
`dataQualityAssertions` reported on that input after it was last written and up to the
end of the step's run, one result per check, whether a check job ran them before the
step or the step ran them itself. An input nothing checked says so. A failed check is
stated and does not withhold the mark, for the reason the assertion history gives: the
chain's mark says where the figure came from rests on evidence, not that the data was
good. The scope statement counts the inputs that carried checks.

Nothing here calls a forge API to resolve a commit. Read-only is a property of what
the code can reach.
