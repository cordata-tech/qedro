Real OpenLineage from [cordata-tech/pipeline-runtime](https://github.com/cordata-tech/pipeline-runtime)
0.2.10, not hand-written.

Captured on 2026-11-14 from the released wheel, with no Docker and no cloud account:

```console
$ python3 -m venv prcapture
$ prcapture/bin/pip install --no-cache-dir 'cordata-pipeline-runtime[run]==0.2.10'
$ mkdir prdemo && cd prdemo && ../prcapture/bin/pipeline-runtime demo .
$ cp out/lineage.ndjson tests/fixtures/pipeline-runtime-0.2.10/pipeline-runtime.ndjson
```

The same three example pipelines as the 0.2.4 capture beside it, and the same six
events. The file is unedited.

What it carries that 0.2.4 did not (qedro#38):

- **`lifecycleStateChange: OVERWRITE` on every output a writer replaces whole**, the
  standard dataset facet, since [pipeline-runtime#15](https://github.com/cordata-tech/pipeline-runtime/issues/15).
  It is the first real capture in this tree that tells `qedro erasure` a descendant
  was rebuilt rather than only written, so
  `tests/test_erasure.py::TestARealEmitterSaysItRebuilt` reads it.
- **`descriptor_path` relative to the domains directory** rather than the absolute
  install location the 0.2.4 capture shows.

It sits beside the 0.2.4 capture rather than replacing it. Six test modules read 0.2.4
for what it carries — the `processing` facet, the publisher fields, the `tags` facet —
and recapturing in place would have changed what each of them measures without any of
them asking for it.
