"""Build `docs/architecture.pdf` from `docs/architecture.md`.

Both files are untracked on purpose, and `MANIFEST.in` excludes both by name:
the architecture is a proposal until it is agreed. This script is tracked so the
PDF can be rebuilt the same way whenever the markdown changes, instead of going
stale beside it.

    python tools/architecture_pdf.py
    python tools/architecture_pdf.py --out /tmp/architecture.pdf

Needs three commands that are not Python dependencies, and says which is
missing rather than failing halfway:

- `mmdc` (mermaid-cli) renders the Mermaid diagrams. To PNG, not SVG, because
  their labels are HTML inside `foreignObject`, which Typst does not draw.
- `pandoc` converts the markdown.
- `typst` is the PDF engine pandoc hands the result to.

The source markdown is never modified. Diagrams and the rewritten copy live in
a temporary directory that is removed afterwards.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "docs" / "architecture.md"
TARGET = REPO / "docs" / "architecture.pdf"
TOOLS = ("mmdc", "pandoc", "typst")

#: Rendered at 3x so diagram labels stay legible when scaled to page width.
SCALE = "3"

#: Taller than this and a diagram cannot share a page with the text around it,
#: so Typst moves it and leaves a near-empty page behind. Wide diagrams take the
#: page width instead.
MAX_HEIGHT = "125mm"

#: Pandoc sets an alignment per table column, which Typst renders centred;
#: left-aligned cells are far easier to read in the module and milestone tables.
#: Ligatures are off in code, so a flag or a path reads one character at a time.
TYPST_HEADER = """\
#show table.cell: set align(left + top)
#set table(inset: (x: 5pt, y: 4pt))
#show table: set text(size: 8.5pt)
#show raw: set text(ligatures: false)
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build docs/architecture.pdf.")
    parser.add_argument("--out", type=Path, default=TARGET, help="where to write the PDF")
    args = parser.parse_args()

    missing = [tool for tool in TOOLS if shutil.which(tool) is None]
    if missing:
        print(f"missing: {', '.join(missing)}", file=sys.stderr)
        return 2
    if not SOURCE.exists():
        # Untracked, so a fresh clone does not have it.
        print(f"{SOURCE.relative_to(REPO)} does not exist in this checkout", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="qedro-architecture-") as tmp:
        work = Path(tmp)
        markdown = _render_diagrams(SOURCE.read_text(), work)
        (work / "architecture.md").write_text(markdown)
        (work / "header.typ").write_text(TYPST_HEADER)
        subprocess.run(
            [
                "pandoc",
                "architecture.md",
                "--from=gfm+attributes",
                "--pdf-engine=typst",
                "--include-in-header=header.typ",
                "--variable=papersize=a4",
                "--variable=fontsize=10pt",
                "--variable=mainfont=Helvetica Neue",
                "--variable=codefont=Menlo",
                "--variable=margin.x=18mm",
                "--variable=margin.y=20mm",
                "--metadata=pagetitle=Qedro architecture",
                f"--output={args.out.resolve()}",
            ],
            cwd=work,
            check=True,
        )

    print(f"wrote {args.out}")
    return 0


def _render_diagrams(markdown: str, work: Path) -> str:
    """Replace each Mermaid block with an image of it, rendered into *work*."""
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        source = work / f"diagram-{count}.mmd"
        image = work / f"diagram-{count}.png"
        source.write_text(match.group(1))
        subprocess.run(
            ["mmdc", "-i", str(source), "-o", str(image), "-s", SCALE, "-b", "white"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        size = f"height={MAX_HEIGHT}" if _is_tall(match.group(1)) else "width=100%"
        return f"![]({image.name}){{{size}}}"

    return re.sub(r"```mermaid\n(.*?)```", replace, markdown, flags=re.DOTALL)


def _is_tall(diagram: str) -> bool:
    """A top-to-bottom flowchart with nested subgraphs runs off the page at full width."""
    return diagram.lstrip().startswith("flowchart TB") and diagram.count("subgraph") >= 2


if __name__ == "__main__":
    sys.exit(main())
