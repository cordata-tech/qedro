# Running qedro on your own lineage

This is the guide for a first run against real events rather than the demo: what you
need before you start, how to keep a copy of your events if the place they go today
cannot give them back, and what the first hour produces. Everything runs on your
machine. qedro reads events and writes files where you tell it to, contacts nothing
except an API address you give it, and sends nothing to Cordata or anyone else
([SECURITY.md](../SECURITY.md) says what it can reach).

If you have not seen it work yet, `qedro demo` writes a fictional company's lineage and
prints the commands to run against it. That takes about a minute and shows what each
output looks like before your own events are involved.

## What you need

- **OpenLineage events**, either as files in a directory or behind a Marquez-compatible
  HTTP API. The emitter does not matter: dbt, Airflow, Spark and Flink are tested against
  real captures ([compatibility.md](compatibility.md) lists versions), and neither a
  cloud provider nor a particular warehouse is involved.
- **Two weeks of events or more.** The projections describe what ran in a window, so a
  weekly job needs at least two runs before its absence means anything, and the quality
  history and erasure check both compare runs over time.
- **Python 3.12 or later**, and `pipx install qedro`.

## Where your events are, and how qedro reads them

| Your events go to | What to do |
|---|---|
| Marquez | Pass its base URL wherever these commands take a directory: `qedro events http://marquez:5000` |
| Files on a disk | Pass the directory. Files must end in `.json`, `.ndjson` or `.jsonl`; other files are skipped, and the skip is not reported yet |
| An S3, GCS or Azure bucket | Copy the prefix to a directory first — `aws s3 sync`, `gcloud storage rsync -r`, `azcopy sync` — and pass that. A reader for buckets is planned but not built |
| A Kafka topic | Keep a copy as below. A Kafka reader is a candidate, not built |
| Google Dataplex, DataHub, OpenMetadata, Microsoft Purview | Keep a copy as below. These turn events into their own model and cannot give them back as they were sent; Dataplex also drops custom facets and keeps 30 days |
| Amazon DataZone / SageMaker Unified Studio | Keep a copy as below. DataZone can return the events it received, and a reader for it is a candidate once it is known whether custom facets survive |
| Nowhere yet | Switch OpenLineage on in your orchestrator with the file transport below, and come back in two weeks |

[compatibility.md](compatibility.md) has the sources for each of these.

## Keeping a copy of your events

OpenLineage clients can send every event to more than one place. A `composite` transport
keeps your current backend exactly as it is and adds a second destination that writes
the raw events, which is what qedro reads. Nothing about the existing backend changes,
and the copy can be removed when the pilot ends.

**dbt (`dbt-ol`), Airflow, and anything else using the Python client.** Put this in
`openlineage.yml`, or point `OPENLINEAGE_CONFIG` at it:

```yaml
transport:
  type: composite
  transports:
    backend:                # what you send to today, unchanged
      type: http
      url: https://lineage.example.internal
    archive:                # the copy qedro reads
      type: file
      log_file_path: /var/lib/openlineage/events
      append: false
```

With `append: false` every event becomes its own file, named
`events-<time>.json`, which qedro reads as it is. With `append: true` the client
writes every event to one file at exactly the path given, so give that path an
`.ndjson` ending or qedro will skip it. This configuration was run with
openlineage-python 1.53.0 and read back by qedro.

`log_file_path` can also be a bucket — `s3://…`, `gs://…`, `az://…` — once
`openlineage-python[fsspec]` and the matching filesystem package (`s3fs`, `gcsfs`,
`adlfs`) are installed wherever the client runs. The client's documentation warns
that object stores may turn appending into overwriting, so keep `append: false`
there. The bucket form has not been run here.

For Airflow, point the provider at the same file with `[openlineage] config_path`, or
set `[openlineage] transport` to the same structure as JSON. The Airflow documentation
has no composite example, and the key names above come from the Python client that the
provider hands its configuration to. The filesystem packages have to be installed on
every worker.

**Spark and Flink** use the Java client, which is configured differently:

- Its `file` transport writes NDJSON to a local path only. On a cluster that is the
  driver's disk, which is rarely where you want it; if it suits, set a `location` ending
  in `.ndjson`.
- For a bucket, the Java client has separate `s3` and `gcs` transports, shipped as the
  `io.openlineage:transports-s3` and `transports-gcs` artefacts rather than inside the
  Spark integration. Each writes one `.json` object per event, named after the event's
  time in milliseconds, and **an event whose name is already taken is dropped** — two
  events in the same millisecond keep only the first.
- The documented composite example for Spark pairs `http` with `kafka`
  (`spark.openlineage.transport.type=composite`, then
  `spark.openlineage.transport.transports.<name>.type=…` per destination). A `file` or
  `s3` child follows the same pattern and has not been run here.

## The first hour

Start by finding out whether your events are readable at all:

```console
$ qedro events ./events
```

On the demo this prints `218 events · 7 jobs · 12 datasets · 3 files  ∎`, and yours
has the same shape. The ∎ means every file parsed and every record was an event. When
it is missing, the lines below the summary say what was skipped and why, and the same
counts decide whether any later output can claim to be complete. Against an API, qedro
stops at 10,000 events and says so, because a window it did not finish reading is not
covered; narrow it with `--since` and `--until`.

Then the Art. 30 record, first with nothing but the events:

```console
$ qedro ropa ./events
```

Expect every activity to say it has no purpose and no legal basis. That is accurate:
lineage records what ran, and none of the standard integrations emits why. The next step
is a `qedro.yaml` naming the controller, your domains, and a purpose and legal basis
for each group of jobs. `qedro demo` writes a commented example, and a first version
covering the jobs that matter most takes an afternoon. Rules match
`namespace/job name` as a pattern, and a job's domain is the last dot-separated part of
its namespace unless a rule sets `domain:`:

```yaml
controller:
  name: Example GmbH
  contact: datenschutz@example.com
domains: [billing, crm]      # a listed domain with no lineage is reported, not ignored
jobs:
  "example.billing/invoices-*":
    purpose: invoicing
    legal_basis: contract
```

```console
$ qedro ropa ./events --config qedro.yaml --out ropa.xlsx
$ qedro ropa ./events --config qedro.yaml --out ropa.json      # keep this one
$ qedro quality ./events --config qedro.yaml
$ qedro provenance ./events --dataset <a table somebody reports from>
$ qedro erasure ./events --dataset <a table you erased from> --since <when>
```

Keep the JSON record. Run the same command a month later and `qedro diff` says what
changed between the two, including a purpose that stopped being emitted even where its
value stayed the same. If you keep a register of processing activities or AI use cases
by hand, `qedro diff register.yaml ropa.json` says where it and the lineage disagree;
`register.yaml` in the demo shows the format.

## What to expect from standard emitters

These gaps are in what dbt, Airflow, Spark and Flink emit today rather than in qedro,
and each output names them rather than filling them in:

- **No ∎ on the Art. 30 record.** Purposes and legal bases come from `qedro.yaml`, so
  every one is marked as asserted. The record earns the mark only when the pipelines
  emit the `processing` facet themselves — [`art30-emit`](https://github.com/cordata-tech/art30-emit)
  adds it to any Python job, and [art30-facet.md](art30-facet.md) describes it.
- **Categories of data and data subjects are blank** unless your datasets carry the
  standard `tags` facet. No integration emits it as of OpenLineage 1.53.0, so the record
  says nobody declared a category rather than that there is no personal data.
- **The provenance chain may name no commit.** It needs `sourceCodeLocation`, which
  none of the captured integrations sent.
- **Erasure usually needs `--since`.** Only the Spark capture carried
  `lifecycleStateChange`, so for dbt and Airflow the moment of erasure is typed by you,
  and the output says it was typed rather than proved. Spark reports every overwrite
  that way, and qedro takes the latest `DROP`, `TRUNCATE` or `OVERWRITE` in the window
  as the erasure. On a table Spark overwrites every night, that is last night's run
  rather than the erasure you mean; the output shows both instants when they differ,
  so check which one it used.

## Telling us how it went

Open an issue on this repository or write to contact@cordata.tech. We do not need your
events or your records. The most useful things to hear are the `qedro events` summary
line, which emitters and versions produced the events, which output answered a
question you actually have, and what you would need next — in particular whether you
would want records kept and compared over months rather than as files you manage
yourself.
