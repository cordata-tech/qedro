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
import subprocess
import sys
import tempfile
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

    with tempfile.TemporaryDirectory() as tmp:
        # The record goes to a temporary file, and the transcript names the path
        # a reader would use rather than the one the capture used. That is the
        # one edit made to the output, and it is made to the *command line*
        # rather than to anything the command printed.
        record = Path(tmp) / "record.json"
        built = _run(
            [
                "ropa",
                "demo/lineage-declared",
                "--config",
                "demo/qedro.yaml",
                "--format",
                "json",
                "--out",
                str(record),
            ],
            cwd=REPO,
        )
        if built.returncode != 0:
            print(f"building the record exited {built.returncode}:\n{built.stderr}", file=sys.stderr)
            return 1
        parts.append(
            "## 1. The record the register is checked against\n\n"
            "```console\n"
            "$ qedro ropa demo/lineage-declared --config demo/qedro.yaml "
            "--format json --out record.json\n"
            f"{built.stdout}```\n"
        )

        result = _run(["diff", "demo/register.yaml", str(record)], cwd=REPO)
        if result.returncode != 0:
            print(f"the comparison exited {result.returncode}:\n{result.stderr}", file=sys.stderr)
            return 1
        parts.append(
            "## 2. Where the register and the record disagree\n\n"
            "```console\n"
            "$ qedro diff demo/register.yaml record.json\n"
            f"{result.stdout.replace(str(record), 'record.json')}```\n"
            f"\nExit status {result.returncode}. The cautions above also go to standard error, "
            "so a run whose output was redirected to a file still shows them.\n"
        )

    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture the register-drift transcript.")
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
