# About qedro: the name, why it exists, and what it is not

## The name

**Q.E.D.** — *quod erat demonstrandum*, "that which was to be demonstrated". The phrase
that closes a proof.

It is not decoration. [Art. 5(2) GDPR](https://eur-lex.europa.eu/eli/reg/2016/679/oj)
places a duty on the controller to be able to **demonstrate** compliance — not to
achieve it quietly, but to show it on request. That is a *demonstrandum*, and producing
it from evidence rather than from assertion is the entire job of this tool.

Mathematicians stopped writing Q.E.D. some time ago. Paul Halmos borrowed a solid square
from magazine typography instead, and it became standard — the **tombstone**, or *halmos*.
It is [U+220E END OF PROOF](https://en.wikipedia.org/wiki/Q.E.D.#Typography), **∎**.

The wordmark puts it where the final letter would go:

```
QEDR∎
```

And it means something at runtime. **The CLI prints `∎` only when the artefact stands on
its own evidence** — never when a job fell back to a mapping file for its `purpose`, and
never when a domain in scope produced no lineage in the window. The run still succeeds
and still writes the file; it simply does not claim to be a proof.

So a complete run finishes the product's name.

## Why this exists

A compliance artefact with holes in it is worse than none, because the holes are
invisible. A RoPA assembled by hand from a wiki, a Confluence page and somebody's memory
looks exactly like one derived from what the platform actually did.

The argument is set out across four posts on [cordata.tech](https://cordata.tech):

- [Fabric + Mesh on AWS](https://cordata.tech/en/blog/fabric-mesh-on-aws) — the account topology and the LF-tag ontology
- [Behaviour-first governance in practice](https://cordata.tech/en/blog/behaviour-first-governance-in-practice) — governance artefacts as byproducts of behaviour
- [A pipeline is a descriptor, not a program](https://cordata.tech/en/blog/pipelines-as-descriptors) and [part 2](https://cordata.tech/en/blog/pipeline-half-openlineage-gx) — the evidence a pipeline emits
- [The catalog is the API](https://cordata.tech/en/blog/governed-mesh-over-mcp) — the read path over that evidence

This is the part those posts stop short of: the code that reads the evidence and produces
the artefact.

## What this is not

**It is not legal advice, and it does not decide compliance.** It reports what the
events say and where each value came from. Whether the resulting record satisfies an
obligation is a judgement for whoever is accountable for it — a data protection officer,
legal counsel, a supervisory authority — and the artefact is written to support that
judgement rather than to stand in for it. Where an article is named in the output, it
says which field the record holds, never that the article is satisfied.

**The record is the controller's, not the tool's.** Art. 30 puts the duty on the
controller, and a generated record is a draft until somebody with that responsibility
reviews and signs it. The tombstone means *this artefact stands on its own evidence*,
which is a statement about provenance, not an approval.

**It covers the processing that emits lineage.** Every record says so, and says which
Art. 30(1) items it has fields for — today (a) the controller and (b) the purposes.
Anything that emits no lineage appears only if it is declared, and a declared activity
is an assertion rather than evidence.

**It is early software.** `0.x` interfaces move between releases, the changelog says
which, and [Apache-2.0](../LICENSE) carries no warranty.

## Design commitments

**No adoption required.** It reads OpenLineage from a directory of JSON or a
Marquez-compatible API. dbt, Airflow, Spark, Flink and Dagster already emit it. Nothing
here needs Cordata's descriptor model, though richer facets produce richer output.

**Not bound to one cloud.** Classification is a source-neutral vocabulary; LakeFormation
LF-tags are one adapter alongside GCP Data Catalog policy tags and Purview
classifications. If `qedro ropa` cannot run against a Marquez instance with no AWS
anywhere in the picture, the neutrality is decorative — so that is an actual test
(`tests/test_cli.py::TestRopaAgainstAnApi`), not an aspiration.

**Flexible by construction, everywhere it is cheap to be.** Multi-cloud, multi-pipeline,
multi-format. Sources are a directory, an S3, GCS or Azure prefix, or any
Marquez-compatible API; config and
vocabulary documents are YAML, JSON or TOML; facets stay raw dictionaries so an emitter
nobody anticipated still arrives intact. Each of these was chosen at the point where
picking one option would have cost nothing today and a rewrite later.

**The vocabulary is data, not types.** Organisations define their own ontologies. Nothing
is compiled against a fixed set of sensitivity levels.

**Read-only by construction.** No write path, no credentials that could acquire one.
