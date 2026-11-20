## What this changes, and why

<!-- What a user would notice, and the reasoning behind the change. The diff shows the how. -->

## Which commitment it keeps

<!-- Only if it touches a path CODEOWNERS lists separately: the tombstone rule, the scope
statement, the vocabularies, the regulation references, what a sign-off covers, the facet
schema or the release workflow. Otherwise delete this section. -->

## Checklist

- [ ] A test for the behaviour, named for what it protects; for a bug fix, it fails without the fix
- [ ] `pytest -q`, `ruff check .` and `ruff format --check .` pass, and `tools/seed.py --check` and `tools/facet_schema.py --check` if they apply
- [ ] A line under `## Unreleased` in `CHANGELOG.md`, and the README or `docs/compatibility.md` if they describe what changed
- [ ] Every commit is signed off (`git commit -s`) and signed

## Did a coding agent help?

<!-- Agents are welcome. If one helped: which tool, what it did, and what you checked
yourself. Name it in a commit trailer too (`Assisted-by: <tool>` or `Co-Authored-By:`).
You are responsible for every line, whatever wrote it. -->

- [ ] No
- [ ] Yes:
