# AGENTS.md

Instructions for a coding agent, or a person, changing this repository. They are the
short form of [CONTRIBUTING.md](CONTRIBUTING.md), which gives the reasons; read it before
anything substantial. Where the two ever disagree, CONTRIBUTING.md is right and this file
is the bug.

Qedro reads OpenLineage events and writes the artefacts an auditor asks for: a GDPR
Art. 30 record, an assertion history, a provenance chain and an erasure record. It is a
CLI that reads evidence and writes files, and nothing else.

## How a change gets in

- **Fork, branch, open a pull request against `main`.** Do not push to `main`, and do not
  create, move or delete a `v*` tag: pushing one publishes to PyPI, where a version can
  never be reused. Releases are the maintainer's.
- **The checks have to pass**, the same ones CI runs on Python 3.12, 3.13 and 3.14:

  ```bash
  pip install -e ".[dev]"
  pip install --no-deps "cordata-pipeline-runtime @ git+https://github.com/cordata-tech/pipeline-runtime@main"
  pytest -q
  ruff check . && ruff format --check .
  python tools/facet_schema.py --check
  python tools/seed.py --check
  ```

- **Add a test for the behaviour you change**, named for what it protects ("the tombstone
  is withheld when a facet came from the mapping file"), not for the function it calls.
- **Add a line under `## Unreleased` in `CHANGELOG.md`**, saying what a user would notice.
- **Sign off every commit** with `git commit -s`. The `Signed-off-by:` line is your
  statement under the [Developer Certificate of Origin](https://developercertificate.org)
  that you may contribute the change under the Apache-2.0 licence; the DCO check fails a
  pull request where a commit lacks one matching its author. **Sign the commit** too, with
  an SSH or GPG key, and explain the reasoning in the message rather than the diff.
- **Agents are welcome, and saying so is welcome too, not required.** If one helped, a
  line in the pull request on what it did and what you checked yourself helps a reviewer
  know where to look; a trailer such as `Assisted-by: <tool>` is fine as well. Either way,
  the person opening the pull request is responsible for every line, has read every
  line, and answers review on it.
- **A pull request that touches a path listed separately in `.github/CODEOWNERS`** says in
  its description which commitment below it keeps.

## Ask before changing these

An agent asks the person it works for before modifying any of these, naming the path and
what the change would do to what a record claims — for example: *"This changes which
fields a sign-off covers, which reopens every existing approval. Do you want that?"* A
small edit here changes what every user's artefacts say.

- `src/qedro/mark.py` — when the tombstone is earned.
- `src/qedro/scope.py` — the scope statement every artefact prints.
- `src/qedro/regulations/` — the regulation's wording, quoted exactly.
- `src/qedro/vocabularies/` — the terms a record may use; some sets are closed by law.
- `COVERED` and `COVERAGE` in `src/qedro/signoff.py` — what a sign-off covers.
- `schemas/` and `tools/facet_schema.py` — the published facet other people's emitters
  implement.
- `.github/workflows/` — `release.yml` publishes to PyPI.

## Never

These are the four commitments, and the changes that most often break them while looking
reasonable.

- **Never make the tombstone `∎` unconditional**, and never add a flag that forces it. It
  means *this artefact stands on its own evidence* and is withheld whenever any part rests
  on assertion — a purpose or legal basis from the mapping file instead of an emitted
  facet, a domain in scope that produced no lineage. The run still succeeds and still
  writes its file. Withholding is the signal. See `src/qedro/mark.py`.
- **Never add a write path** into anything Qedro reads, or a credential that could
  acquire one. No HTTP method but `GET`, no call to a forge to check a commit or a
  signature. Read-only is a property of what the code can reach.
- **Never name a classification source in the model.** LakeFormation, Purview, GCP Data
  Catalog and OpenMetadata are adapters; `lf_tags` and the like stay out of every type
  and field name. `qedro ropa` must run against a Marquez instance with no cloud at all.
- **Never compile a vocabulary into types.** Terms, and the regulation a record answers
  to, are documents loaded at runtime (`src/qedro/vocabularies/`,
  `src/qedro/regulations/`). Nothing in the code knows what a lawful basis is.

And, from how the code is built:

- **Never type a facet.** Core event fields are typed; facets stay raw dictionaries, and a
  projection copes with a facet being absent.
- **Never merge the kinds of facet.** Job and run facets say what ran; dataset facets are
  true of the dataset whoever looks; input and output facets describe one run's use of a
  dataset, which is where `dataQualityAssertions` lives. *This table has a unique key* is a
  claim; *the run on the 10th checked it and it held* is evidence.
- **Never raise on bad lineage.** Parsing skips and *counts* records it cannot use, and the
  count reaches the completeness decision. What the *user* wrote — a config, a vocabulary —
  does raise. `src/qedro/errors.py` is the line.
- **Never edit generated files by hand**: `demo/` comes from `src/qedro/demo/` via
  `tools/seed.py`, and `schemas/openlineage-art30-processing-facet.json` from
  `tools/facet_schema.py`.
- **Never let an explanation judge.** `src/qedro/explain.py` says where a value came from,
  built only from facts the record holds. No *valid*, *lawful*, *compliant* or *correct*;
  `tests/test_explain.py` fails on them.
- **Never paraphrase the regulation.** `src/qedro/regulations/gdpr.yaml` quotes it
  character for character, punctuation included. Change a quote only against the
  official EUR-Lex text, and say in the pull request which one you compared with.
- **Never change what a sign-off covers by accident.** A sign-off hashes an explicit list
  of fields per projection (`COVERED` in `src/qedro/signoff.py`). A new JSON field goes
  beside those paths, not inside one, unless the change means to reopen every existing
  approval — in which case `COVERAGE` moves up and the changelog says so.

## How to work here

What has caught real defects in this repository, rather than general advice:

- **A bug fix starts with a failing test**, and you check it fails without the fix. Then
  break the behaviour on purpose and watch the test go red: a test that passes either way
  protects nothing.
- **Run the projections against the real captures** in `tests/fixtures/`, not only
  synthetic events. The dbt, Airflow and Spark captures there produced five issues and
  four bugs between them.
- **Check an OpenLineage facet or field name against the spec** before you use it, rather
  than writing the name it seems it should have. A plausible name that does not exist is
  the error that looks most like work.
- **One concern per pull request.** No reformatting, renaming or tidying along the way;
  they hide the change a reviewer needs to see.
- **No new runtime dependency without an issue first.** The base install is two packages
  on purpose, and each one more is a supply-chain path into a tool that holds evidence.
- **Documentation moves with behaviour**: the README when a command or output changes,
  `docs/compatibility.md` when what Qedro runs against changes, the changelog always.
- **Security problems go to [SECURITY.md](SECURITY.md)**, never a public issue.

## Every artefact, every format

- **States its own scope**, on every run, including one that earns the mark.
- **Prints in all formats a projection supports.** A renderer is one `singledispatch`
  function per format in `src/qedro/render.py`; `tests/test_render.py` runs every format
  against every projection, so a change to one format usually needs the others.
- **Stays byte-for-byte reproducible.** No generation timestamp in any document: the same
  events must give the same file, or every comparison reports a change that is not one.

## Where things are

- `src/qedro/` — one module per projection (`ropa`, `quality`, `provenance`, `erasure`,
  `deployer`), plus `compare` (`qedro diff`), `signoff` (`qedro sign`), `staleness`
  (`qedro status --against`), `explain`, `render`, `pdf`, `xlsx`, `sources` (reading
  events) and `config`.
- `tests/fixtures/` — real captures from dbt, Airflow and Spark. A new emitter's capture,
  with a README naming its version and the command that produced it, is a welcome
  contribution on its own.
- `docs/compatibility.md` — what Qedro runs against. A row says `works` only when a test
  names it.

Python 3.12 is the floor; do not add workarounds for older versions.
