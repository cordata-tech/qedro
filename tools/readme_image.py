"""Draw `docs/images/art30-pdf.png`, the two records at the top of the README.

The demo's two sets of lineage are the same pipelines, identical apart from the
`processing` facet. Rendered as Art. 30 PDFs, one earns the mark and the other
says why it does not, and the first page of each, side by side, shows that
difference faster than a paragraph can.

    python tools/readme_image.py

Needs `qedro[pdf]` and, for rasterising, `pypdfium2` and `pillow`. Neither is a
dependency of qedro, so this is not run in CI: rerun it by hand whenever the
first page of the Art. 30 PDF changes, and look at the result.
"""

from __future__ import annotations

import argparse
import os
import sys
from io import BytesIO
from pathlib import Path

import pypdfium2
from PIL import Image, ImageDraw

from qedro import config as config_module
from qedro import declared, render, ropa, vocabulary
from qedro.sources import read

ROOT = Path(__file__).resolve().parent.parent

#: How much of each first page to show: the controller, the verdict and the
#: overview of the activities, with the start of the first activity faded out.
SHOWN = 0.6
SCALE = 1.6
#: Millimetres of each page edge cropped away, out of the 20 mm margin.
TRIM = 13
GAP, MARGIN, FADE = 40, 32, 90
BACKGROUND = (238, 241, 244)
BORDER = (203, 210, 217)


def record(lineage: str, *, activities: bool) -> bytes:
    """The Art. 30 record of one of the demo's two sets of lineage, as a PDF.

    Built as `qedro ropa demo/<lineage> --config demo/qedro.yaml` builds it, from
    the repository root, so the scope names the source as a reader would type it.
    """
    settings = config_module.load("demo/qedro.yaml")
    words = vocabulary.load(settings.vocabulary or None)
    entries = declared.load("demo/activities.yaml", vocabulary=words) if activities else ()
    events, report = read(f"demo/{lineage}")
    built = ropa.build(events, config=settings, vocabulary=words, report=report, declared=entries)
    return render.pdf(built)


def first_page(pdf: bytes) -> Image.Image:
    page = pypdfium2.PdfDocument(pdf)[0].render(scale=SCALE).to_pil().convert("RGB")
    # Most of the page's 20 mm margins go: the README shows the image at well
    # under its width, and every pixel of margin is one the text does not get.
    trim = int(page.width * TRIM / 210)
    shown = page.crop((trim, trim, page.width - trim, int(page.height * SHOWN)))
    # Fade the cut edge into the background, so the crop reads as *more below*
    # rather than as a page that ends mid-table.
    fade = Image.new("L", shown.size, 255)
    draw = ImageDraw.Draw(fade)
    for i in range(FADE):
        draw.line(
            [(0, shown.height - FADE + i), (shown.width, shown.height - FADE + i)],
            fill=int(255 * (1 - i / FADE)),
        )
    out = Image.new("RGB", shown.size, BACKGROUND)
    out.paste(shown, mask=fade)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draw the README's image of the Art. 30 PDF.")
    parser.add_argument("--out", default=str(ROOT / "docs" / "images" / "art30-pdf.png"))
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    os.chdir(ROOT)

    pages = [
        first_page(record("lineage-declared", activities=False)),
        first_page(record("lineage", activities=True)),
    ]
    width = sum(p.width for p in pages) + GAP + 2 * MARGIN
    height = max(p.height for p in pages) + 2 * MARGIN
    canvas = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    x = MARGIN
    for page in pages:
        canvas.paste(page, (x, MARGIN))
        # A hairline down the sides and along the top; the bottom is the fade.
        right, bottom = x + page.width - 1, MARGIN + page.height - FADE
        draw.line([(x - 1, bottom), (x - 1, MARGIN - 1), (right + 1, MARGIN - 1)], fill=BORDER)
        draw.line([(right + 1, MARGIN - 1), (right + 1, bottom)], fill=BORDER)
        x += page.width + GAP

    out.parent.mkdir(parents=True, exist_ok=True)
    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    out.write_bytes(buffer.getvalue())
    print(f"wrote {out} ({len(buffer.getvalue()) // 1024} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
