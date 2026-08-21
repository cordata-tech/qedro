# Qedro — working notes

Turns emitted evidence into the artefacts an auditor asks for. Reads OpenLineage,
produces a DSGVO Art. 30 record of processing activities, an assertion history, and
the provenance chain from a published number back to the signed commit that
authorised it.

Planning lives in `cordata-tech/platform`: **#25** is the epic, **#27** is v1. Read
#27 before starting anything substantial — the scope and the sequencing are there,
and the design constraints below were each argued out in its comments.

## Four commitments that must not erode

These are the ones that get quietly simplified away. Each has a reason that is not
obvious from the code.

**Classification is source-neutral. Never `lf_tags`.** LakeFormation is one adapter
beside GCP Data Catalog policy tags, Purview classifications and OpenMetadata terms.
The whole reason projections were sequenced ahead of the control plane is that they
work against infrastructure people already run; a tool requiring LakeFormation has
re-acquired the precondition that inversion removed. **Naming is where the coupling
sneaks back in.** Acceptance test: `qedro ropa` must run against a Marquez instance
with no AWS anywhere.

**The vocabulary is data the tool loads, never types it is compiled against.** Three
separate requirements land on this one decision — source-neutrality, organisations
authoring their own ontologies through a UI later, and shipping recommended starter
ontologies. All three are free if a vocabulary document is loaded at runtime; all
three need a rewrite of everything touching a tag if `sensitivity` is an enum.

**The tombstone is earned, not printed.** `∎` means *this artefact stands on its own
evidence*. It is withheld whenever a job's `purpose` or `legal_basis` came from the
mapping fallback rather than an emitted facet, or a domain in scope produced no
lineage in the window. The run still succeeds and still writes the file — it simply
does not claim to be a proof. **Withholding is the signal**; a mark printed on every
success says nothing. This is also the answer to a problem the published post raises
and does not solve: a compliance artefact with holes is worse than none *because the
holes are invisible*. See `qedro/mark.py`, and do not make it unconditional.

**Read-only by construction.** No write path in any handler, and no credential that
could acquire one. Not a policy — a property of what the code is able to reach.

## Facets, and why the model is shallow

Core event fields are typed; **facets stay raw dictionaries**. OpenLineage has a long
tail of facets and every emitter populates a different subset, so modelling them all
means breaking whenever one moves. A projection asks for the facet it wants and copes
with absence.

Related: **parsing never raises.** Production lineage contains events from emitters
that disagree with the spec. Bad records are skipped and *counted*, and the count
reaches `ReadReport` → the summary line → the completeness decision. That chain is
relied on downstream, not diagnostics.

## The other two repos

| Repo | Answers | Binding |
|---|---|---|
| [`pipeline-runtime`](https://github.com/cordata-tech/pipeline-runtime) | *What should this pipeline do, and did it?* | AWS-native by design. LF-tags are correct there |
| `catalog-mcp` (planned, platform#26) | *What is the policy on this dataset, right now?* | AWS-native by design |
| **this** | *What happened, and can I prove it to an auditor?* | **must not be** |

`pipeline_runtime.descriptor` is the shared governance vocabulary. When the Art. 30
facet schema lands here it is **generated from `Processing`, never written beside it**
— the published posts claim in public that one model has three consumers, so a fourth
that derives is evidence for the claim and a fourth that restates is a counterexample
to it. A test should fail when they diverge.

## Conventions

- **Apache-2.0.** Everything open, including the parts that would be a commercial tier
  elsewhere. `pipeline-runtime` is MIT and that inconsistency is deliberate — the
  patent grant is what DACH enterprise legal review looks for.
- **Private until v0.1.** The repo opens when the reader works, a projection produces
  real output, and a release cadence exists — not before. A public repo with no
  commits behind it signals less than no repo.
- Commit identity is `laszlo@cordata.tech`, signed. **No assistant commit trailers.**
- `ruff check` + `ruff format` + `pytest`. CI runs 3.12 and 3.13, and asserts the
  wordmark keeps `role="img"`, `aria-label` and a `<title>`.
- Python floor is 3.12. `datetime.fromisoformat` handles `Z` natively there; do not
  add normalising workarounds for older versions.

## The name and the mark

**Q.E.D.** — *quod erat demonstrandum*. Art. 5(2) GDPR obliges a controller to
**demonstrate** compliance, which makes the artefact a *demonstrandum*.

The wordmark is **QEDR∎** — the Halmos tombstone standing in where the final letter
goes, so a complete run finishes the product's name.

`docs/wordmark.svg` draws the square as a `<rect>`, not the U+220E glyph: font
coverage for END OF PROOF is thin and a missing glyph renders the logo as `QEDR□`.
Text width is pinned with `textLength` because the font stack falls back on GitHub and
positioning against assumed metrics put the square on top of the R once already.
**Verify any wordmark change by rendering it** — `rsvg-convert -w 700 -b white
docs/wordmark.svg -o /tmp/wm.png` — rather than by reading coordinates.

Naming history is platform#30: roughly 140 candidates, and **Atrium, Aktum and
Aktario each looked clean on PyPI, npm, GitHub and the open web and died in the
trademark register.** Do not re-propose them.

## A known gap

Cross-repo claims drift. The published posts cite this code, and twice in one day a
post asserted something the repo contradicted — a fabricated `Dataset` import, and a
`resolve_lf_tag` example validating a key the ontology did not define. **When code
here changes in a way a post describes, check the post.** Nothing automatic catches it.
