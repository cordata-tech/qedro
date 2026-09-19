Real OpenLineage from `art30-emit`, not hand-written.

`events.jsonl` is one run of the worked example in
[`cordata-tech/art30-emit`](https://github.com/cordata-tech/art30-emit) —
`examples/nightly-export`, a cron script that reads one table and writes a CSV
somebody else collects — captured on 2026-09-19 with `art30-emit` 0.1.0 and
`openlineage-python` 1.53.0. Nothing was removed.

Two events, `START` and `COMPLETE`, and both name the same datasets.

## Why this capture exists when four others already do

The dbt, Airflow, Spark and Flink captures are lineage from systems that emit it
already. This one is the opposite case: code no integration can reach, which is the
gap the second column of `docs/compatibility.md` is about. Two things are here and
nowhere else in `tests/fixtures`.

**The `processing` facet from a second emitter.** Until this capture, every event
carrying `purpose` and `legal_basis` came from `pipeline-runtime`, so a change that
only worked against that one producer's spelling would have passed. The facet here is
generated from the published schema by a package that shares no code with it.

**Classification on the wire.** No integration emits `TagsDatasetFacet` as of 1.53.0
— `openlineage-python` has shipped the class since 1.52.0, but the repository builds
job and run tag facets only — so the Art. 30(1)(c)–(f) path added in #13 was
exercised against generated events alone. Here it is read from a real one, including
the distinction the projection keeps and the demo cannot show cleanly: the source
table is classified `retention: P7Y` and the file written from it `retention: P30D`,
so *reads* and *writes* carry different values for one key in one activity.

## What the record built from it looks like

Every field except recipients and security measures comes from these two events, so
`qedro ropa` earns the mark. `tests/test_ropa.py::TestTheArt30EmitCapture` asserts
that, which is what lets the emitter row in `docs/compatibility.md` say `works` —
the rule in #5 is that the test naming a row lives here, not in the thing being
claimed about.

The emitter's own repository has the other half: `tools/capture_example.py --check`
re-runs the example against `qedro` from PyPI and fails its build when the output
moves. Neither check makes the other redundant; this one fails when Qedro stops
reading what that emitter sends, and that one fails when the emitter stops sending
what Qedro reads.

## One thing to know before regenerating it

The dataset `s3://acme-exports/consent/nightly.csv` is namespace `s3://acme-exports`
and name `consent/nightly.csv`. An emitter splitting that at the first slash would
produce namespace `s3:`, which is a dataset nobody can find again — the example is
what found that bug in `art30-emit`, and the capture holds both sides to it.
