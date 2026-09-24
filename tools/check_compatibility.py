"""Hold `docs/compatibility.md` to the rule it states about itself.

That page opens with a rule: **a row may only say `works` if a test names it and
would fail if it broke.** Everything in this project rests on the argument that a
claim without evidence is worth less than no claim, and a compatibility matrix is
nothing but claims — so the rule is the page's whole value, and it was being kept
by hand. See cordata-tech/qedro#5.

Two things are checked, and each has been broken in practice:

**A `works` row names a test.** In September a row was marked `works` on the
strength of a test in another repository, which could go green on output this
tool cannot read.

**A named test exists.** A row naming a test that has been renamed away is worse
than a row naming none, because it looks checked. This script was written after
naming `tests/test_declared.py`, which has never existed.

    python tools/check_compatibility.py

Exits non-zero and says which row, which is the only interface it needs.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "docs" / "compatibility.md"

#: A test node id as the page spells one: a file, optionally a class, optionally
#: a function. Matched rather than parsed, because the page is prose with tables
#: in it and anything stricter would need the page to be written for the script.
NODE = re.compile(r"tests/test_[a-z_]+\.py(?:::[A-Za-z_][A-Za-z0-9_]*)*")

#: Rows allowed to say `works` without naming a test, and why. Each one is a
#: claim about something that is not Python behaviour, so there is nothing a test
#: could assert — kept here rather than as a pattern in the page, so that adding
#: an exemption is a change somebody reviews.
WITHOUT_A_TEST = {
    "3.12, 3.13, 3.14": "the CI matrix is the evidence, and it is in the workflow file",
}


def rows(text: str) -> list[tuple[int, str]]:
    """Table rows, with their line numbers. Headers and separators dropped."""
    out = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped) <= set("|- "):
            continue
        out.append((number, stripped))
    return out


def main() -> int:
    text = PAGE.read_text(encoding="utf-8")
    table_rows = rows(text)

    problems: list[str] = []

    # 1. Every `works` row names a test, or is exempt for a stated reason.
    for number, row in table_rows:
        if "**works**" not in row:
            continue
        if NODE.search(row):
            continue
        label = row.split("|")[1].strip() if row.count("|") > 1 else row
        # The legend at the top of the page defines what each state means. Its
        # first cell *is* the state word, which is how it is told apart from a
        # row making a claim.
        if label in {"**works**", "**planned**", "**candidate**", "**no**"}:
            continue
        if any(key in label for key in WITHOUT_A_TEST):
            continue
        problems.append(
            f"{PAGE.name}:{number}: says **works** and names no test — "
            f"the row is {label!r}. A row with no test is `candidate`, "
            "however finished the code feels"
        )

    # 2. Every test the page names exists. Collected rather than grepped: a test
    #    that exists in a file but errors on import is not one that would fail if
    #    the row broke, and collection is what tells the difference.
    named = sorted(set(NODE.findall(text)))
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    for node in named:
        if not any(line.startswith(node) for line in collected):
            problems.append(
                f"{PAGE.name} names {node}, which does not collect — "
                "a row naming a test that has been renamed away looks checked "
                "and is not"
            )

    if problems:
        print("docs/compatibility.md does not keep its own rule:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(
        f"docs/compatibility.md keeps its rule: "
        f"{len(named)} named tests collect, every `works` row names one"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
