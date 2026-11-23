# Proving an erasure reached what was derived from it

![A tree of six datasets descended from warehouse/crm_raw.contacts, erased on 22 July. Each box names its dataset, its state, and what ran it and where it lives, with an icon for each kind and a legend below: two rebuilt since the erasure, two written without saying how, and two tinted — marketing.audiences, only appended to, and billing_curated.dunning_cases, not written since the erasure. Each edge names the job that derived the dataset below it.](images/erasure-tree.png)

*What an erasure reached, from the erasure record's PDF
(`qedro erasure docs/examples/erasure --dataset crm_raw.contacts --out erasure.pdf`).
Each dataset derived from the erased one says whether a job has replaced it since; the
tinted ones still hold what the erasure removed upstream.*

Art. 17 needs three things and this does one of them. Finding where a subject's data
lives is a catalog's job; deleting it is an orchestrator's, and never this tool's.
Proving it happened — and saying where the proof does not reach — is what lineage is
actually for, because every failure mode is a derived dataset somebody forgot: the
materialised view, the monthly rollup, the vector index that already ingested the row.

`qedro erasure` walks the graph forwards from the erased dataset:

```console
$ qedro erasure demo/lineage-declared --dataset crm_raw.contacts
Erasure of warehouse/crm_raw.contacts

    tombstone     2026-07-22T09:18:00+00:00 — emitted overwrite, not a drop or truncate

    warehouse/crm_curated.customers
      platform      dbt · PostgreSQL
      state         written 2026-07-26T01:36:00+00:00 — 4 runs since the tombstone
      how           not reported, so not shown to have replaced the contents

      warehouse/billing_curated.invoices
        platform      Airflow · PostgreSQL
        state         written 2026-07-26T04:06:00+00:00 — 4 runs since the tombstone
        how           not reported, so not shown to have replaced the contents

        warehouse/billing_curated.dunning_cases
          platform      dbt · PostgreSQL
          state         not written since the tombstone

  this record does not claim to be a proof:
    ! 1 of 3 descendants has not been written since the tombstone:
      warehouse/billing_curated.dunning_cases
```

The weekly dunning job has not run since the erasure, so one branch of the closure is
a place the proof does not reach. **That list is the output.** A record where
everything had been written in time would be a record nobody needs.

**A write is not necessarily a replacement.** An incremental model adds to a table on
each run and leaves what it held before the erasure where it was. qedro counts a
descendant as **rebuilt** where the event says the contents were replaced — an
`OVERWRITE`, `TRUNCATE` or `DROP` lifecycle state, or dbt's `table` or `view`
materialisation — and as **only appended to** where dbt says `incremental` or
`snapshot`, which withholds the mark and names the dataset. Most emitters say neither,
and then the descendant is counted as **written**, with a line saying how it was
written was not reported. dbt does not report `--full-refresh`, so a full refresh of an
incremental model reads as an append, which errs toward withholding.

The demo's erasure is a straight chain, so it shows two of those states. The tree at
the top of this page is the same projection run against `docs/examples/erasure`, a
small set of events that branches and shows all of them; `--out erasure.pdf` draws it.

**The tombstone is evidence or an assertion.** OpenLineage already has the facet —
`lifecycleStateChange`, whose `DROP`, `TRUNCATE` and `OVERWRITE` values are erasures
and whose `ALTER`, `CREATE` and `RENAME` values are not. An erasure job that emits it
gives an instant somebody proved. `--since` gives the same instant typed by hand, works
against any lineage at all, and withholds the mark, because every write below is then
measured against a date rather than an event. It does not cut the read: what descends
from the erased dataset is known from runs before the erasure, and a descendant nothing
has written since is the one the record most needs to name.

**An overwrite is weaker evidence than a drop or a truncate.** Spark reports
`OVERWRITE` on every overwriting write, so on a table rewritten nightly most of those
events are routine. qedro counts the completed runs that dropped, truncated or
overwrote the dataset, prefers a drop or truncate where there is one, and with
`--since` takes the first after it — the first run that could have carried out the
request. Without `--since` it takes the latest, and withholds the mark when that is one
of several overwrites, since nothing then says which run was the erasure.

**It reports datasets, not rows.** It can show that a dataset descends from the erased
one and that a job wrote it afterwards. It cannot show that a particular data
subject's rows are gone, because no lineage event carries that — and a tool that blurred
the two would be producing the artefact this project exists to argue against. The
sentence is in the scope statement of every run, including one that earns the mark.
