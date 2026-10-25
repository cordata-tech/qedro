Real OpenLineage from [cordata-tech/pipeline-runtime](https://github.com/cordata-tech/pipeline-runtime)
0.2.5, run from a **git checkout** rather than the wheel, not hand-written.

The point of it is the commit. Run from a wheel, pipeline-runtime has no repository to
ask, and from 0.2.5 sends neither `descriptor_git_commit` nor its signed flag — the
case `tests/fixtures/pipeline-runtime-0.2.4` covers, from the release before, when the
flag was sent as `false` with no commit. Run from a checkout, each producing run names
the commit its descriptor was at and whether that commit is signed, which is what
`qedro provenance` needs to tie a verdict to a commit (#33).

Captured on 2026-10-25:

```console
$ git clone --branch v0.2.5 https://github.com/cordata-tech/pipeline-runtime.git /tmp/prgit/src
$ cd /tmp/prgit/src
$ python3 -m venv /tmp/prgit/venv && /tmp/prgit/venv/bin/pip install --editable '.[run]'
$ /tmp/prgit/venv/bin/python -m tools.seed
$ for p in fraud/pipelines/transactions_scored policy/pipelines/claims_ingest \
           finance/pipelines/merchant_settlement; do
    CORDATA_LINEAGE_OUT=/tmp/prgit/lineage.ndjson \
      /tmp/prgit/venv/bin/python -m pipeline_runtime example/domains/$p.yml
  done
$ cp /tmp/prgit/lineage.ndjson tests/fixtures/pipeline-runtime-0.2.5-checkout/pipeline-runtime.ndjson
```

At 0.2.5, `pipeline-runtime demo` did not work from an editable checkout — it looked
for the example descriptors inside the installed package, and in the source tree they
are at the repository root — so the three pipelines were run one by one, as that
repository's README describes. Six events, unedited.

That was fixed in pipeline-runtime 0.2.7 (pipeline-runtime#14), so a refresh can be one
command from a clone's editable install, `pipeline-runtime demo DIR`. 0.2.6 and 0.2.7
change what an installed copy emits, not what a checkout does, so this capture is still
what a checkout run produces, and nothing requires refreshing it.

**`signed: true` depends on the machine that captured it.** pipeline-runtime asks git
whether the descriptor's commit is signed, and git answers from its own signature
configuration. The commits at `v0.2.5` are SSH-signed, and the capturing machine had
the signer in its allowed-signers file; elsewhere the same run could report `false`.
That is why the verdict is evidence about one run, and why qedro takes it from the
event rather than re-deriving it.

Compared with the 0.2.4 wheel capture: the `.validate` jobs' inputs now carry the
`tags` facet (pipeline-runtime#10), so only the two raw sources nothing in the demo
writes are unclassified; and `descriptor_path` is relative to the repository root, as
its schema says, because the argument given was relative (pipeline-runtime#12).
