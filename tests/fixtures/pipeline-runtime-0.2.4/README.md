Real OpenLineage from [cordata-tech/pipeline-runtime](https://github.com/cordata-tech/pipeline-runtime)
0.2.4, not hand-written.

Captured on 2026-10-23 from the released wheel, with no Docker and no cloud account:

```console
$ python3 -m venv /tmp/prcapture
$ /tmp/prcapture/bin/pip install --no-cache-dir 'cordata-pipeline-runtime[run]==0.2.4'
$ mkdir /tmp/prdemo && cd /tmp/prdemo && /tmp/prcapture/bin/pipeline-runtime demo .
$ cp out/lineage.ndjson tests/fixtures/pipeline-runtime-0.2.4/pipeline-runtime.ndjson
```

`pipeline-runtime demo` runs the emitter's three example pipelines — fraud scoring,
claims ingest and merchant settlement — and writes six events, a COMPLETE for each
pipeline and an OTHER for each `.validate` job. The file is unedited.

What it carries that the 0.1.0 capture it replaced did not (#31):

- **`processing` on every job**, including the three `.validate` jobs, which 0.1.0 sent
  with no facets at all ([pipeline-runtime#9](https://github.com/cordata-tech/pipeline-runtime/issues/9)).
- **`source_published_by` and `source_published_release`** on `cordata_provenance`, with
  `source_table` and `source_schema_version`, naming the application release behind
  what each pipeline read ([pipeline-runtime#2](https://github.com/cordata-tech/pipeline-runtime/issues/2), qedro#25).
- **The standard `tags` dataset facet** on what each pipeline writes, with the keys
  `sensitivity`, `domain`, `residency` and `subject_type`
  ([pipeline-runtime#3](https://github.com/cordata-tech/pipeline-runtime/issues/3)).
  The two Art. 30 keys reach the record; the other two are the emitter's own.

Two things in it come from capturing from a wheel rather than a git checkout.
`descriptor_path` is the temporary install location above, and no commit is named,
yet `descriptor_git_commit_signed` is `false` rather than absent — see qedro#33.

Hand-written fixtures agree with whatever the parser already does. This one does not,
which is the point of it.
