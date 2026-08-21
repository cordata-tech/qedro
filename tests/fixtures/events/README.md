Real OpenLineage, not hand-written.

`pipeline-runtime.ndjson` is emitted by
[cordata-tech/pipeline-runtime](https://github.com/cordata-tech/pipeline-runtime)
running its two example pipelines. It carries the standard `schema` dataset
facet, plus that project's two custom facets — `processing` on the job
(DSGVO Art. 30: purpose and legal basis) and `cordata_provenance` on the run
(descriptor hash, git commit, whether the commit was signed).

Hand-written fixtures agree with whatever the parser already does. This one
does not, which is the point of it.
