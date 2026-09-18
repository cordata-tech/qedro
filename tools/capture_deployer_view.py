"""Capture `docs/evidence/deployer-view.md`, the transcript platform#48 § 13 quotes.

The point of a captured transcript is that it is what the command printed, so this
runs the installed CLI and writes its output unedited. It **refuses a dirty working
tree**: the file names the commit that produced it, and that name is worth nothing if
uncommitted changes were in the tree at the time.

    python tools/capture_deployer_view.py            # rewrite the transcript
    python tools/capture_deployer_view.py --check     # fail if it is out of date

`tests/test_demo.py::TestTheDeployerViewOnTheDemo` asserts the facts in it — the use
case, the model versions and run counts, the provenance of purpose and legal basis,
and whether the mark is earned — but not the wording, so a change to how the output
reads leaves this file describing the commit it names until it is recaptured.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "docs" / "evidence" / "deployer-view.md"

RUNS = [
    (
        "Lineage whose pipelines do not declare, with purpose and basis from the mapping file",
        ["ropa", "demo/lineage", "--config", "demo/qedro.yaml", "--view", "deployer"],
    ),
    (
        "The same three weeks once the pipelines declare",
        ["ropa", "demo/lineage-declared", "--config", "demo/qedro.yaml", "--view", "deployer"],
    ),
    (
        "The same record with declared activities that emit no lineage",
        [
            "ropa",
            "demo/lineage-declared",
            "--config",
            "demo/qedro.yaml",
            "--view",
            "deployer",
            "--activities",
            "demo/activities.yaml",
        ],
    ),
]

PREAMBLE = """# Transcript: `qedro ropa --view deployer`

Captured by script from qedro {version}, at commit `{commit}` with a clean working tree,
on Python {python}. The output below is what the command printed, unedited. Run the same
commands from the repository root to reproduce it.

The three runs use the same config and differ in one thing each. The first reads
`demo/lineage`, where purpose and legal basis come from the mapping file. The second
reads `demo/lineage-declared`, where the pipelines emit them. The third adds
`demo/activities.yaml`, which declares two uses that emit no lineage: a support
assistant, which names a model and is listed, and a payroll SaaS, which names none and
belongs only in the Art. 30 record.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the deployer-view transcript.")
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args()

    dirty = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.check:
        print(
            "working tree is dirty; commit first so the transcript can name the commit it came from",
            file=sys.stderr,
        )
        return 2

    from qedro import __version__

    commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    python = ".".join(str(n) for n in sys.version_info[:3])

    parts = [PREAMBLE.format(version=__version__, commit=commit, python=python)]
    for number, (title, argv) in enumerate(RUNS, 1):
        result = subprocess.run(
            [sys.executable, "-P", "-m", "qedro", *argv],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,  # a non-zero exit is reported below, not raised
        )
        if result.returncode != 0:
            print(f"run {number} exited {result.returncode}:\n{result.stderr}", file=sys.stderr)
            return 1
        parts.append(
            f"## {number}. {title}\n\n```console\n$ qedro {' '.join(argv)}\n{result.stdout}```\n"
            f"\nExit status {result.returncode}.\n"
        )

    captured = "\n".join(parts)
    if args.check:
        current = TARGET.read_text()
        # The header names a version, a commit and a Python build, all of which move
        # for reasons that are not a change in the output.
        if _body(current) != _body(captured):
            print(
                f"{TARGET.relative_to(REPO)} is out of date: the command prints something else now",
                file=sys.stderr,
            )
            return 1
        print(f"{TARGET.relative_to(REPO)} matches what the command prints")
        return 0

    TARGET.write_text(captured)
    print(f"wrote {TARGET.relative_to(REPO)} from qedro {__version__} at {commit}")
    return 0


def _body(text: str) -> str:
    """Everything from the first run onwards, which is the part the output decides."""
    marker = "## 1. "
    return text[text.index(marker) :] if marker in text else text


if __name__ == "__main__":
    sys.exit(main())
