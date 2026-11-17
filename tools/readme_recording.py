"""Finish the README's recording: the terminal, then the PDFs it wrote (#46).

`vhs tools/readme_recording.tape` records the terminal into
`build/readme-recording/terminal.gif`: a real install from PyPI, `qedro demo`, and
the three records written as PDF. A terminal cannot show a PDF, so this appends two
closing frames rendered from the same demo events, the way `tools/readme_image.py`
renders the stills: the first page of the two Art. 30 records side by side, then the
first page of the erasure record with its tree. It writes `docs/images/demo.gif`.

    vhs tools/readme_recording.tape
    python tools/readme_recording.py

Needs what `tools/readme_image.py` needs — `qedro[pdf]`, `pypdfium2` and `pillow` —
and is run by hand for the same reason. Rerun both steps whenever the commands'
output or the first page of either PDF changes.
"""

from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageSequence

# Beside this file, so on the path when it is run as a script.
import readme_image
from qedro import config as config_module
from qedro import erasure, render
from qedro.sources import read

ROOT = Path(__file__).resolve().parent.parent
TERMINAL = ROOT / "build" / "readme-recording" / "terminal.gif"
OUT = ROOT / "docs" / "images" / "demo.gif"

#: How long each closing frame is held, in milliseconds.
HOLD = 4500


def erasure_pdf() -> bytes:
    """The demo's erasure record, as the recording's last command writes it."""
    settings = config_module.load("demo/qedro.yaml")
    events, report = read("demo/lineage-declared")
    built = erasure.build(
        events, dataset="warehouse/crm_raw.contacts", config=settings, report=report
    )
    return render.pdf(built)


def fitted(image: Image.Image, size: tuple[int, int], background: tuple[int, ...]) -> Image.Image:
    """*image* scaled to fit inside *size*, centred on *background*."""
    scale = min(size[0] / image.width, size[1] / image.height)
    shown = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    out = Image.new("RGB", size, background)
    out.paste(shown, ((size[0] - shown.width) // 2, (size[1] - shown.height) // 2))
    return out


def main() -> int:
    os.chdir(ROOT)
    if not TERMINAL.exists():
        print(f"no {TERMINAL.relative_to(ROOT)} — run vhs tools/readme_recording.tape first",
              file=sys.stderr)  # fmt: skip
        return 1

    terminal = Image.open(TERMINAL)
    frames = [f.copy() for f in ImageSequence.Iterator(terminal)]
    durations = [f.info.get("duration", 40) for f in ImageSequence.Iterator(Image.open(TERMINAL))]
    size = frames[0].size

    closing = [
        readme_image.side_by_side(
            [
                readme_image.first_page(readme_image.art30("lineage-declared", activities=False)),
                readme_image.first_page(readme_image.art30("lineage", activities=True)),
            ]
        ),
        readme_image.side_by_side([readme_image.first_page(erasure_pdf())]),
    ]
    for image in closing:
        frame = fitted(image, size, readme_image.BACKGROUND)
        frames.append(frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
        durations.append(HOLD)

    buffer = BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    OUT.write_bytes(buffer.getvalue())
    seconds = sum(durations) / 1000
    print(
        f"wrote {OUT.relative_to(ROOT)} ({len(buffer.getvalue()) // 1024} KB, {seconds:.0f} s)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
