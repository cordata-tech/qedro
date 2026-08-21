<img src="docs/wordmark.svg" alt="Qedro" width="240">

**Turns emitted evidence into the artefacts an auditor asks for.**

Point it at OpenLineage events you already emit. Get back a DSGVO Art. 30 record of
processing activities, an assertion history, and the provenance chain from a published
number to the signed commit that authorised it.

```console
$ qedro ropa --since 2026-01-01 --out ropa.xlsx
  47 jobs · 12 domains · 3 legal bases
  wrote ropa.xlsx                                                              ∎
```

> [!NOTE]
> Early development. The event reader is the current work; the projections are not
> built yet. Watch the repository rather than depending on it.

## The name

**Q.E.D.** — *quod erat demonstrandum*, "that which was to be demonstrated". The phrase
that closes a proof.

It is not decoration. [Art. 5(2) GDPR](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679)
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

## Design commitments

**No adoption required.** It reads OpenLineage from a directory of JSON or a
Marquez-compatible API. dbt, Airflow, Spark, Flink and Dagster already emit it. Nothing
here needs Cordata's descriptor model, though richer facets produce richer output.

**Not bound to one cloud.** Classification is a source-neutral vocabulary; LakeFormation
LF-tags are one adapter alongside GCP Data Catalog policy tags and Purview
classifications. If `qedro ropa` cannot run against a Marquez instance with no AWS
anywhere in the picture, the neutrality is decorative.

**The vocabulary is data, not types.** Organisations define their own ontologies. Nothing
is compiled against a fixed set of sensitivity levels.

**Read-only by construction.** No write path, no credentials that could acquire one.

## Licence

[Apache-2.0](LICENSE). Everything, including the parts that would be the commercial
tier elsewhere.
