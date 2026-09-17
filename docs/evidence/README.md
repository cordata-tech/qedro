# Evidence

Artefacts that published writing quotes. Each one was captured from a real run, and the capture is committed beside any trimmed copy so the trimming can be checked.

## `deployer-view.md`

The transcript of `qedro ropa --view deployer` that `cordata-tech/platform#48` § 13 quotes, captured on 2026-09-17 at commit `e284804`. A script runs the installed CLI from the repository root and writes what each command printed, unedited, together with its exit status. The script refuses to run on a dirty working tree, so the commit named in the file is the code that produced the output.

The three runs share one config and change one input each: `demo/lineage`, where purpose and legal basis come from the mapping file; `demo/lineage-declared`, where the pipelines emit them and the view earns the mark; and the same with `demo/activities.yaml`, where one declared AI use is marked `declared, no lineage` and the mark is withheld. `tests/test_demo.py::TestTheDeployerViewOnTheDemo` asserts the same facts — the use case, both model versions and their run counts, the inputs, the provenance of purpose and legal basis, and whether the mark is earned — but not the wording. A later change to how the output reads leaves this file describing the commit it names, which is why it names one.

## `fraud-events.captured.ndjson` and `fraud-event.trimmed.json`

Captured on 2026-09-17 from [`pipeline-runtime`](https://github.com/cordata-tech/pipeline-runtime) at commit `15b6110`, running the fraud example as that repository's README describes:

```console
$ ./.venv/bin/python -m tools.seed
$ CORDATA_LINEAGE_OUT=fraud-events.captured.ndjson \
    ./.venv/bin/python -m pipeline_runtime example/domains/fraud/pipelines/transactions_scored.yml
```

The run wrote two events. The COMPLETE event for `cordata.fraud/transactions-scored-daily` (run `8ea56885-df09-4694-b730-98a39d900644`) carries all three of the following on that one event:

| Field | Value | Where it is on the event |
|---|---|---|
| `model_version` | `2026-07-fraud-v3` | `run.facets.cordata_provenance.step_params.score` |
| `purpose` | `fraud-detection` | `job.facets.processing` |
| `legal_basis` | `legitimate-interest` | `job.facets.processing` |

The second event is the OTHER event for the `.validate` job. It carries the data-quality assertions and none of the three fields.

`fraud-event.trimmed.json` is derived from the capture by a script that asserts the three values against the captured event rather than against the descriptor. It keeps the event's identity (type, time, producer, job, run id, inputs and outputs) and removes everything else, including the envelope keys `_producer` and `_schemaURL`. Anything not in the trimmed copy is in the capture.

These files are a record of one run and are not regenerated. A later run produces a different run id and event time.
