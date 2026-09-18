# Qedro — working notes

Turns emitted evidence into the artefacts an auditor asks for. Reads OpenLineage,
produces a GDPR (DSGVO) Art. 30 record of processing activities, an assertion history, and
the provenance chain from a published number back to the signed commit that
authorised it. All three projections are built.

Planning lives in this repository: **#1** is the epic, **#2** is v1, **#3** constrains
what any projection's output must contain. Read #2 before starting anything
substantial — the scope and the sequencing are there, and the design constraints
below were each argued out in its comments. `docs/architecture.md` is the map of
the modules and the rule each one keeps — **untracked on purpose** until the target
architecture is agreed, so it lives in the working copy and not in the history. The same
goes for `docs/architecture.pdf`; rebuild it with `python tools/architecture_pdf.py`
whenever the markdown changes (needs `mmdc`, `pandoc` and `typst`).

Both were transferred from `cordata-tech/platform` on 2026-08-21, so their comment
history refers to them as `#25` and `#27` and to Qedro as *Atrium* and briefly
*Aktario*. Three closed issues stay in `platform` because they span more than this
repo: **platform#29** (which LF-tag ontology is authoritative), **platform#30** (the
naming search) and **platform#26** (`catalog-mcp`, which has no repo yet).

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

**Three kinds of facet, and the difference matters.** Job and run facets describe
what ran. Dataset facets describe the dataset and are true whoever is looking.
**Input and output facets describe one run's use of a dataset** — `dataQualityAssertions`
lives there, which is why `quality` can speak in dates and why the parser dropped it
until that projection needed it. Do not merge the two: *this table has a unique key*
is a claim, *the run on the 10th checked it and it held* is evidence.

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

`pipeline_runtime.descriptor` is the shared governance vocabulary. The Art. 30 facet
schema is **generated from `Processing`, never written beside it** — the published
posts claim in public that one model has three consumers, so a fourth that derives is
evidence for the claim and a fourth that restates is a counterexample to it.
`tools/facet_schema.py` does the generating and `tests/test_facet_schema.py` fails when
they diverge. Only the prose is written here, and a field with no prose stops the
generator rather than shipping undocumented.

The runtime is a dev dependency installed **`--no-deps`, pinned to `main`** — see the
CI step. `descriptor.py` imports pydantic and nothing else, so pulling duckdb, pandas,
pyarrow and great-expectations in to read a type declaration is not a trade worth
making; and a pinned tag would defer noticing that the model moved to whoever bumped
the pin, which is the one thing the test exists to catch.

## Conventions

- **Apache-2.0.** Everything open, including the parts that would be a commercial tier
  elsewhere. `pipeline-runtime` is MIT and that inconsistency is deliberate — the
  patent grant is what DACH enterprise legal review looks for.
- **Public since 2026-09-18, and on PyPI as `qedro` 0.2.0.** It was private until the
  checkpoint at the end of v0.2: run against real work first, then open. 0.1.0 was
  tagged on 2026-08-22 and never published, and that wait paid — the real dbt, Airflow
  and Spark captures produced #8, #9, #12, #22 and #23 before anything shipped. The
  commercial analysis moved to a private issue in `platform` before the repository
  opened; what is here is engineering. **Anything committed now is public immediately**,
  and **pushing a `v*` tag publishes to PyPI** through trusted publishing, so a tag is
  a release decision rather than a bookkeeping step.
- **The version has one source**, `qedro.__version__`; `pyproject.toml` reads it with
  `dynamic = ["version"]`. The release workflow fails if the tag disagrees with it, or
  if `CHANGELOG.md` has no entry for it.
- Commit identity is `laszlo@cordata.tech`, signed. **No assistant commit trailers.**
- **`jj` is colocated with git.** Work in `jj` — `jj new -m "…"`, `jj describe`, `jj git
  push` — and let it write the git commits; the repo-level jj config carries the same
  identity and SSH signing key, so a change made either way is indistinguishable in the
  history. Plain `git` still reads and writes the same working copy.
- `ruff check` + `ruff format` + `pytest`. CI runs 3.12, 3.13 and 3.14, and asserts
  the wordmark keeps `role="img"`, `aria-label` and a `<title>`.
- **Shared shapes live in shared modules.** `scope.py` (what a run looked at),
  `words.py` (saying a number correctly) and `Config.domain_for` were each three
  copies before they were one. A renderer is one `singledispatch` function per
  format, so a projection added later inherits the scope statement and the mark
  rather than reimplementing them — `tests/test_render.py` parametrises over
  format *and* projection for exactly that reason.
- **`demo/` is generated.** `tools/seed.py` writes both estates and CI runs it with
  `--check`; editing an event by hand looks like it worked until the next
  regeneration reverts it. The two estates must stay identical apart from the
  `processing` facet — that equivalence is the whole demonstration, and
  `tests/test_demo.py` asserts it.
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
