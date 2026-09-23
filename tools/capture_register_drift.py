"""Capture `docs/evidence/register-drift.md`, the transcript platform#48 quotes.

The AI Readiness pillar refuses a parallel AI governance programme on the grounds
that its register drifts from the Art. 30 record within two quarters. That is a
claim, and this is it run against two documents a reader can open: `demo/register.yaml`
and the record generated from `demo/lineage-declared`. See cordata-tech/qedro#24.

The point of a captured transcript is that it is what the command printed, so this
runs the installed CLI and writes its output unedited. It **refuses a dirty working
tree**: the file names the commit that produced it, and that name is worth nothing if
uncommitted changes were in the tree at the time.

    python tools/capture_register_drift.py            # rewrite the transcript
    python tools/capture_register_drift.py --check    # fail if it is out of date

`tests/test_register.py::TestTheDemoRegister` asserts the four findings in it — the
row that is still true, the purpose the pipeline changed, the row for a pipeline that
no longer exists and the model nobody can evidence — but not the wording, so a change
to how the output reads leaves this file describing the commit it names until it is
recaptured.
"""

from __future__ import annotations

import argparse
import difflib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "docs" / "evidence" / "register-drift.md"

PREAMBLE = """# Transcript: `qedro diff` against a hand-maintained register

Captured by script from qedro {version}, at commit `{commit}` with a clean working tree,
on Python {python}. The output below is what the command printed, unedited. Run the same
commands from the repository root to reproduce it.

`demo/register.yaml` is an AI register of four rows, maintained by a separate
governance workstream eighteen months ago. `demo/lineage-declared` is three weeks of
lineage from pipelines that declare their purpose and lawful basis. Neither document
knows about the other, which is the situation
[platform#48](https://github.com/cordata-tech/platform/issues/48) describes.

**Four rows, four outcomes.** One is still true and reports nothing. One names a
purpose the pipeline stopped having. One describes a pipeline that no longer exists.
One names a model version in production that no run has ever reported — which is the
claim refusal (b) rests on, and the only one of the four that a parallel register
cannot fix by being more diligent, because nothing in the platform emits it.

Note what the comparison does **not** do. It prints no mark: ∎ means *this artefact
stands on its own evidence*, and a comparison's evidence is two documents it cannot
verify. It reports each document's own verdict instead, and a register has none —
which the output says rather than leaving blank.
"""


def _run(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-P", "-m", "qedro", *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,  # a non-zero exit is reported by the caller, not raised
    )


def capture() -> str | int:
    from qedro import __version__

    commit = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    python = ".".join(str(n) for n in sys.version_info[:3])
    parts = [PREAMBLE.format(version=__version__, commit=commit, python=python)]

    # `record.json` in the repository root, not a temporary directory, and
    # removed again below. The path is printed by the first command *and* is one
    # of the values the second one wraps its scope statement around, so a long
    # temporary path wraps differently from a short one and no two machines
    # produce the same transcript. Rewriting the path afterwards cannot fix that:
    # by then the line breaks have already been decided. A fixed relative path is
    # also what a reader would type.
    record = REPO / "record.json"
    if record.exists():
        # It is removed again below, so a file already there belongs to somebody
        # and this script is not entitled to it.
        print(f"{record} already exists; move it out of the way first", file=sys.stderr)
        return 2
    try:
        built = _run(
            [
                "ropa",
                "demo/lineage-declared",
                "--config",
                "demo/qedro.yaml",
                "--format",
                "json",
                "--out",
                "record.json",
            ],
            cwd=REPO,
        )
        if built.returncode != 0:
            print(
                f"building the record exited {built.returncode}:\n{built.stderr}", file=sys.stderr
            )
            return 1
        parts.append(
            "## 1. The record the register is checked against\n\n"
            "```console\n"
            "$ qedro ropa demo/lineage-declared --config demo/qedro.yaml "
            "--format json --out record.json\n"
            f"{built.stdout}```\n"
        )

        result = _run(["diff", "demo/register.yaml", "record.json"], cwd=REPO)
        if result.returncode != 0:
            print(f"the comparison exited {result.returncode}:\n{result.stderr}", file=sys.stderr)
            return 1
        parts.append(
            "## 2. Where the register and the record disagree\n\n"
            "```console\n"
            "$ qedro diff demo/register.yaml record.json\n"
            f"{result.stdout}```\n"
            f"\nExit status {result.returncode}. The cautions above also go to standard error, "
            "so a run whose output was redirected to a file still shows them.\n"
        )
    finally:
        record.unlink(missing_ok=True)

    return "\n".join(parts)


def _dirty() -> str:
    """Uncommitted changes, ignoring the captured transcripts themselves.

    The check exists so the commit named in the file is the code that produced
    the output. A transcript sitting uncommitted is not that code — and there is
    more than one of them, so recapturing both in one go would otherwise have
    each refusing because of the other.
    """
    status = subprocess.run(
        ["git", "-C", str(REPO), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return "\n".join(line for line in status if "docs/evidence/" not in line).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the register-drift transcript.")
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args()

    dirty = _dirty()
    if dirty and not args.check:
        print(
            "working tree is dirty; commit first so the transcript can name the commit it came from",
            file=sys.stderr,
        )
        return 2

    captured = capture()
    if isinstance(captured, int):
        return captured

    if args.check:
        current = TARGET.read_text() if TARGET.exists() else ""
        # The header names a version, a commit and a Python build, all of which move
        # for reasons that are not a change in the output.
        if _body(current) != _body(captured):
            print(
                f"{TARGET.relative_to(REPO)} is out of date: the command prints something else now",
                file=sys.stderr,
            )
            # What differs, not only that something does. A check that fails on
            # a machine the author is not sitting at is worth little if finding
            # out why means reproducing that machine.
            for line in difflib.unified_diff(
                _body(current).splitlines(),
                _body(captured).splitlines(),
                fromfile="committed",
                tofile="this run",
                lineterm="",
            ):
                print(line, file=sys.stderr)
            return 1
        print(f"{TARGET.relative_to(REPO)} matches what the command prints")
        return 0

    TARGET.write_text(captured)
    print(f"wrote {TARGET.relative_to(REPO)}")
    return 0


def _body(text: str) -> str:
    """Everything from the first run onwards, which is the part the output decides."""
    marker = "## 1. "
    return text[text.index(marker) :] if marker in text else text


if __name__ == "__main__":
    sys.exit(main())
