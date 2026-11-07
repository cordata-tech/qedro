# Evidence

Artefacts that published writing quotes. Each one was captured from a real run, and the capture is committed beside any trimmed copy so the trimming can be checked.

## `deployer-view.md`

The transcript of `qedro ropa --view deployer` that `cordata-tech/platform#48` § 13 quotes, recaptured on 2026-09-18 from qedro 0.2.0, the version on PyPI, at commit `645bd4f`. `tools/capture_deployer_view.py` runs the installed CLI from the repository root and writes what each command printed, unedited, together with its exit status. It refuses to run on a dirty working tree, so the commit named in the file is the code that produced the output, and `--check` fails when the command prints something else.

The first capture was on 2026-09-17 at `0fc4e54`, from 0.1.0, which was never released. It went out of date when English output moved from DSGVO to GDPR and long scope values began wrapping, which is what `--check` is for.

The three runs share one config and change one input each: `demo/lineage`, where purpose and legal basis come from the mapping file; `demo/lineage-declared`, where the pipelines emit them and the view earns the mark; and the same with `demo/activities.yaml`, where the declared support assistant is marked `declared, no lineage` and the mark is withheld. The document also declares a payroll SaaS, which names no model and so appears only in the Art. 30 record. `tests/test_demo.py::TestTheDeployerViewOnTheDemo` asserts the same facts — the use case, both model versions and their run counts, the inputs, the provenance of purpose and legal basis, and whether the mark is earned — but not the wording. A later change to how the output reads leaves this file describing the commit it names, which is why it names one.

## `register-drift.md`

The transcript `cordata-tech/platform#48` quotes for refusal (b): an AI register checked against the record the pipelines produced, showing that a register nobody runs drifts from what actually happens. `tools/capture_register_drift.py` builds the record from `demo/lineage-declared`, runs `qedro diff demo/register.yaml` against it, and writes what both commands printed. It refuses a dirty working tree for the same reason the deployer capture does, and `--check` fails when the output moves.

`demo/register.yaml` is four rows and four outcomes, none of them invented for the demo. One is still true and reports nothing, so the transcript contains agreement as well as drift — a report where everything disagrees teaches a reader to distrust the tool rather than the register. One names a purpose the pipeline stopped having. One describes a pipeline that no longer exists, and names the owner who would have closed the row. One names a model version in production that no run has ever reported, which is the only one of the four a more diligent register could not have fixed, because nothing in the platform emits it.

`tests/test_register.py::TestTheDemoRegister` asserts those four findings and not the wording, so the same rule applies as above: a change to how the output reads leaves this file describing the commit it names until it is recaptured. Both transcripts are checked in CI.

## `erasure.md` and `erasure-overwrites/`

The transcripts `cordata-tech/platform#18` quotes for the Art. 17 post, recaptured on 2026-11-07 from qedro 0.11.0 at `4577f39`, whose `src/` is the 0.11.0 release. Each of the three commands was also run with the 0.11.0 wheel installed from PyPI, the same day, and printed the same output byte for byte.

It has been captured three times, and each recapture changed wording rather than any verdict. The first, on 2026-11-04 from 0.10.1 at `974b238`, ended run 2b *every descendant was rewritten after an emitted erasure*; 0.10.2 (`f1fa0e4`) made that *after the emitted overwrite*, because the tombstone line above it says the overwrite was not a drop or truncate. 0.11.0 (#35) stopped calling a descendant *rewritten*, since none of these events says whether a write replaced the contents or appended to them: each is now *written*, with a `how` line saying how was not reported, the propagation line counts *written without saying how*, and the verdicts end *written after the emitted …*. The scope statement's last sentence changed to match. Which descendants count as reached, and whether each record earns the mark, is the same in all three. `tools/capture_erasure.py` writes the file, refuses a dirty working tree, and with `--check`, which CI runs, fails when either the output or the generated input moves.

**Run 1** reads `demo/lineage-declared`, where the demo's `acme.crm/subject-erasure` job emits `lifecycleStateChange`, so the erasure instant is evidence rather than a typed `--since`, and the weekly dunning job is the descendant the erasure has not reached. Compared with qedro 0.5.0, the release current when platform#18 first described this run, one thing changed: the tombstone line reads *emitted overwrite, not a drop or truncate* where it read *emitted overwrite*, since 0.7.0 (#29). Nothing else in the run differs.

**Runs 2a and 2b** read `erasure-overwrites/events.ndjson`, which is **synthetic** and generated by the same script, because the demo overwrites no table on a schedule. It is five nights of a Spark job overwriting `crm_curated.contacts_snapshot`, with the facet on START, RUNNING and COMPLETE as `openlineage-spark` 1.53.0 sends it in `tests/fixtures/spark-4.2.0`, and a daily job reading the snapshot each morning. Without `--since`, the latest of five overwrites is taken and the mark is withheld with a reason saying to pass one; with `--since 2026-07-22T10:00:00Z`, the window starts at the request, the first of the two overwrites after it is taken, and the record earns the mark. The scope states the number of candidates and how the one used was chosen; it does not list them individually. `tests/test_erasure.py::TestChoosingTheErasureAmongSeveral` asserts the same rule against events built in the test.

## `fraud-events.captured.ndjson` and `fraud-event.trimmed.json`

Captured on 2026-09-17 from [`pipeline-runtime`](https://github.com/cordata-tech/pipeline-runtime) **0.1.0**, at commit `15b6110` — the events' `producer` says so — running the fraud example as that repository's README describes:

```console
$ ./.venv/bin/python -m tools.seed
$ CORDATA_LINEAGE_OUT=fraud-events.captured.ndjson \
    ./.venv/bin/python -m pipeline_runtime example/domains/fraud/pipelines/transactions_scored.yml
```

The run wrote two events. The model version on it, `2026-07-fraud-v3`, is also the name the demo's later scoring model carries, so the two artefacts agree about which model they show. The COMPLETE event for `cordata.fraud/transactions-scored-daily` (run `8ea56885-df09-4694-b730-98a39d900644`) carries all three of the following on that one event:

| Field | Value | Where it is on the event |
|---|---|---|
| `model_version` | `2026-07-fraud-v3` | `run.facets.cordata_provenance.step_params.score` |
| `purpose` | `fraud-detection` | `job.facets.processing` |
| `legal_basis` | `legitimate-interest` | `job.facets.processing` |

The second event is the OTHER event for the `.validate` job. It carries the data-quality assertions and none of the three fields.

`fraud-event.trimmed.json` is derived from the capture by a script that asserts the three values against the captured event rather than against the descriptor. It keeps the event's identity (type, time, producer, job, run id, inputs and outputs) and removes everything else, including the envelope keys `_producer` and `_schemaURL`. Anything not in the trimmed copy is in the capture.

These files are a record of one run and are not regenerated. A later run produces a different run id and event time.

**They stay at 0.1.0 on purpose** (#31). A 0.2.4 run carries the same three values on the COMPLETE event, but its `.validate` event now carries `purpose` and `legal_basis` too ([pipeline-runtime#9](https://github.com/cordata-tech/pipeline-runtime/issues/9)), so the sentence above about the second event — which `cordata-tech/platform#48`'s published pillar also makes — is true of this capture and not of a new one. Replacing the capture would make a published caption false without anyone editing it. The tests read a 0.2.4 capture instead, in `tests/fixtures/pipeline-runtime-0.2.4`. If the pillar is revised, re-capture then and change both together.
