# Contributing

Issues and pull requests are welcome. Most of this page is about scope and about
four commitments that look like details and are not, because the quickest way to
waste an afternoon here is to send something good that cannot be merged.

## What this repo is for

Producing compliance artefacts from evidence a platform already emits, and being
honest about the parts it cannot evidence. That second half decides most of what
follows.

## Especially welcome

**A case where the tombstone is printed and should not be.** The mark means *this
artefact stands on its own evidence*. If you can construct a run that earns it
while something is unproven, that is the most valuable bug report this project
can receive, and a failing test is worth more than a fix.

**Lineage from an emitter we have not seen.** Production events disagree with the
spec in ways nobody predicts. A file that the reader mishandles — or handles
while quietly skipping records — is exactly what `tests/fixtures/` is for.

**A projection's output read by somebody who does the job.** A DPO, an auditor, a
data steward saying *this column is not what I would ask for* is worth more than
any amount of internal reasoning about it.

**A source adapter.** `sources.read()` dispatches on scheme behind one entry
point. A new source yields `Event` objects and stores nothing.

## Out of scope

- **Any write path into a system Qedro reads.** See below; this is not
  negotiable.
- **A server, a database, a UI.** Not because they are bad ideas — there is a
  design for them — but because they are not this repository. It stays a CLI
  that reads evidence and writes a file.
- **Resolving a commit or a signature over the network.** `provenance` reports
  what an emitter reported. A projection that phoned a forge would have acquired
  a credential and a network dependency, and the tool would no longer be
  read-only by construction.
- **Modelling more facets as types.** Core event fields are typed; facets stay
  raw dictionaries. See the rule below.

## Four commitments that must not erode

Each of these has been argued out, and each will look like an unnecessary
constraint at some point.

**Classification is source-neutral.** LakeFormation is one adapter beside GCP
Data Catalog policy tags, Purview classifications and OpenMetadata terms — never
the shape of the model, and never a name in the code. The acceptance test is
that `qedro ropa` runs against a Marquez instance with no AWS anywhere
(`tests/test_cli.py::TestRopaAgainstAnApi`).

**The vocabulary is data the tool loads, never types it is compiled against.**
`src/qedro/vocabularies/dsgvo.yaml` is a starting point, not a standard. Point
`--vocabulary` at your own and the shipped one is replaced wholesale. Nothing in
the code knows what a lawful basis is.

**The tombstone is earned, not printed.** It is withheld whenever any part of an
artefact rests on assertion rather than evidence, and **withholding is the
signal** — a mark printed on every successful run says nothing. Do not make it
unconditional, and do not add a flag that forces it.

**Read-only by construction.** No write path in any handler, and no credential
that could acquire one. This is a property of what the code is able to reach,
not a policy it follows. The HTTP source can only build `GET`.

## Ground rules

**Facets stay raw dictionaries.** OpenLineage has a long tail of them and every
emitter populates a different subset, so a projection asks for the facet it
wants and copes with absence. Typing them means breaking whenever one moves.

**Parsing never raises.** A directory of production lineage contains events that
disagree with the spec, and a reader that dies on the first is useless. Bad
records are skipped and **counted**, and the count reaches the completeness
decision. That chain is relied upon, not diagnostics.

**What the user wrote does raise.** A config typo silently produces an artefact
with a hole in it, which is worse than a traceback. `errors.py` is the line
between the two.

**Every artefact states its own scope**, on every run, including one that earns
the mark. A scope statement that appeared only when coverage was poor would
teach a reader that its absence means full coverage. See
[#3](https://github.com/cordata-tech/qedro/issues/3).

**Two files are generated and CI checks both.** `schemas/openlineage-art30-processing-facet.json`
comes from `pipeline_runtime.descriptor.Processing` via `tools/facet_schema.py`,
and `demo/` comes from `tools/seed.py`. Editing either by hand looks like it
worked until the next regeneration reverts it.

## Running things

```bash
pip install -e ".[dev]"
pytest -q
ruff check . && ruff format --check .
python tools/facet_schema.py --check
python tools/seed.py --check
```

Python 3.12 is the floor; CI runs 3.12, 3.13 and 3.14.

Two test modules import `pipeline_runtime`, which is not on PyPI — the Art. 30
facet schema is generated from its `Processing` model and a test fails when the
two diverge. Install it the way CI does, or skip those two:

```bash
pip install --no-deps "cordata-pipeline-runtime @ git+https://github.com/cordata-tech/pipeline-runtime@main"
```

The import is unconditional on purpose. A skip when the module is absent would
mean CI silently stops checking the thing the test exists for.

## Commits and pull requests

**Explain the reasoning, not the diff.** The diff is in the diff. A commit
message here is for the person who finds this code in a year and wants to know
why it is shaped this way — especially when the answer is *we tried the obvious
thing and it was wrong*.

**Sign your commits.** `git config commit.gpgsign true` with an SSH or GPG key.
A project about provenance that accepts unsigned commits is making a point it
would rather not.

**Tests that read as sentences.** Test names in this repository describe the
behaviour being protected, not the function being called, and the ones guarding a
commitment say which commitment. Follow that; it is why the suite is readable.

**How a change gets in.** Fork, branch, open a pull request against `main`. CI
runs the suite on Python 3.12, 3.13 and 3.14 and has to pass before a merge, and
`main` takes no force pushes and cannot be deleted. `.github/CODEOWNERS` requests
a review automatically, and lists separately the paths where a change is easy to
make and expensive to get wrong — the tombstone rule, the scope statement, the
vocabularies, the published facet schema and the release workflow. A pull request
touching one of those is worth a sentence in its description about which
commitment it keeps.

## Adding a source, an emitter or a catalog

`docs/compatibility.md` says what Qedro runs against, and a row may only say `works`
when a test names it. That rule decides when something new gets built, so the queue in
[#5](https://github.com/cordata-tech/qedro/issues/5) is **pulled by evidence rather
than pushed by a release**: an integration nobody runs cannot carry a test that would
fail if it broke, and shipping one on a schedule produces exactly the row that page
exists to prevent.

**Emitters are the exception, and captures are welcome any time.** Nothing in the code
changes for a new emitter — anything emitting OpenLineage is readable. The work is
capturing a real run, which costs about an hour in Docker, needs no account, and finds
defects: the dbt, Airflow and Spark captures in `tests/fixtures/` produced five issues
and four bugs between them. A capture with a README naming the emitter version and the
command that produced it is a good first contribution, and it is what lets a row say
`works`.

**Sources and catalog adapters are pulled by somebody who runs the thing**, because
each brings a credential and a dependency. If you have events in a bucket or on a
topic, or classification in a catalog that no emitter is tagging datasets from, say so
on #5 — that is the trigger, and the design decisions waiting for it are written there.

## Releases

`0.x` versions may change interfaces between releases, and the changelog says
which. Output formats and the `qedro.yaml` schema are the parts most likely to
move before `1.0`.

Releases happen when something is worth releasing rather than on a calendar, and
each one is a tag, a changelog entry and a PyPI artefact. `main` is expected to
be releasable at any point: CI runs on every push, and a red `main` is a bug
before it is anything else.

Pushing a `v*` tag is what publishes. The workflow refuses to ship if the tag
disagrees with `qedro.__version__`, or if the changelog entry for that version
is missing or still marked unreleased.
