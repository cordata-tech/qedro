"""PDF output, for the people who receive a record rather than run qedro (#37).

An auditor or a supervisory authority files it and cites it later; a data
protection officer signs it and forwards it. It carries what every other format
carries — the findings, the scope statement, and the mark or the reasons it is
withheld — and, where the record is a graph, a diagram of it that shows evidence
state. Lineage tools already draw lineage; what none of them draws is which part
of the graph an erasure demonstrably reached.

Three properties are held here and tested:

- **The same events give the same bytes.** reportlab's `invariant` mode leaves
  out the creation date and the random document id, so a PDF is reproducible
  from its inputs, as the JSON is.
- **No font of our own.** reportlab ships Bitstream Vera, which covers the
  dashes and quotes qedro prints but not U+220E, so the mark is drawn as a
  filled square — the same reason `docs/wordmark.svg` draws it as a `<rect>`.
- **A state is a word before it is a colour.** Every node in a diagram is
  labelled, so the page reads in grey print and to a reader who does not
  distinguish the tint.

reportlab is an optional extra, imported by the caller in `render`, so a run
that produces text never pays for it.
"""

from __future__ import annotations

import io
import os
from collections.abc import Sequence
from typing import Any
from xml.sax.saxutils import escape

import reportlab
from reportlab.graphics.shapes import Drawing, Group, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import __version__

FONT, BOLD = "QedroVera", "QedroVeraBold"
_FONTS = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
if FONT not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont(FONT, os.path.join(_FONTS, "Vera.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD, os.path.join(_FONTS, "VeraBd.ttf")))

INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#52606D")
RULE = colors.HexColor("#CBD2D9")
#: The tint the workbook uses where the proof does not reach, so the two
#: artefacts mark the same thing the same way.
UNREACHED = colors.HexColor("#FDF0D5")

WIDTH = A4[0] - 40 * mm

BODY = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12, textColor=INK)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.5, leading=10, textColor=MUTED)
TITLE = ParagraphStyle("title", parent=BODY, fontName=BOLD, fontSize=15, leading=19)
HEADING = ParagraphStyle(
    "heading", parent=BODY, fontName=BOLD, fontSize=10.5, leading=14, spaceBefore=10, spaceAfter=4
)
VERDICT = ParagraphStyle("verdict", parent=BODY, fontName=BOLD, fontSize=10, leading=13)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8, leading=10, alignment=TA_LEFT)


def _p(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(escape(text), style)


class _Mark(Flowable):
    """The tombstone, drawn: Vera has no glyph for U+220E."""

    def __init__(self, size: float = 7.5) -> None:
        super().__init__()
        self.size = size
        self.width = self.height = size

    def draw(self) -> None:
        self.canv.setFillColor(INK)
        self.canv.rect(0, 0, self.size, self.size, stroke=0, fill=1)


def _verdict(record: Any, earned: str) -> list[Flowable]:
    """The mark and the sentence it ends, or the reasons it is withheld.

    First on the page, as the workbook puts it in the cell the file opens on.
    """
    if record.complete:
        sentence = f"{earned[0].upper()}{earned[1:]}."
        # The mark follows the sentence it finishes, as in the terminal.
        text_w = min(pdfmetrics.stringWidth(sentence, BOLD, VERDICT.fontSize) + 8, WIDTH - 14)
        row = Table([[_p(sentence, VERDICT), _Mark()]], colWidths=[text_w, 14], hAlign="LEFT")
        row.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    *[
                        (side, (0, 0), (-1, -1), 0)
                        for side in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")
                    ],
                ]
            )
        )
        return [row]
    out: list[Flowable] = [_p("This record does not claim to be a proof:", VERDICT)]
    out += [_p(f"• {reason}") for reason in record.completeness.reasons]
    return out


def _scope(scope: Any) -> list[Flowable]:
    """The scope statement, unconditionally, as every format prints it (#3)."""
    rows = [("Source", scope.source or "unknown"), ("Window", scope.window())]
    rows += [(label[0].upper() + label[1:], value) for label, value in scope.statement()]
    table = Table(
        [[_p(label, CELL), _p(value, CELL)] for label, value in rows],
        colWidths=[32 * mm, WIDTH - 32 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
                ("FONTNAME", (0, 0), (0, -1), BOLD),
            ]
        )
    )
    return [_p("Scope of this record", HEADING), table, Spacer(1, 6), _p(scope.OUT_OF_VIEW, SMALL)]


def _document(title: str, body: Sequence[Flowable], *, footer: str) -> bytes:
    buffer = io.BytesIO()

    def page(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 12 * mm, footer)
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=title,
        author="",
        creator=f"qedro {__version__}",
        invariant=1,
    )
    doc.build(list(body), onFirstPage=page, onLaterPages=page)
    return buffer.getvalue()


# --- erasure ---------------------------------------------------------------

#: The word each state is drawn with, matching the text renderer's `state` line.
STATE_LABEL = {
    "rebuilt": "rebuilt since the erasure",
    "written": "written, how not reported",
    "appended": "only appended to",
    "": "not written since the erasure",
}


def _state(descendant: Any) -> str:
    if descendant.how == "" and descendant.incomplete:
        return "not known — a run never finished"
    return STATE_LABEL[descendant.how]


def _tree(record: Any) -> Drawing:
    """The closure from the erased dataset down, one box per dataset.

    A tidy layout of the simplest kind: leaves take columns in walk order, a
    parent sits over the middle of its children, and depth is the row. Scaled
    down to the page width when the closure is wide, never up.
    """
    descendants = list(record.descendants)
    children: dict[str, list[Any]] = {}
    for d in descendants:
        children.setdefault(d.parent or record.dataset, []).append(d)

    column: dict[str, float] = {}
    next_leaf = [0.0]

    def place(key: str) -> float:
        kids = children.get(key, [])
        if not kids:
            column[key] = next_leaf[0]
            next_leaf[0] += 1
        else:
            spots = [place(k.dataset) for k in kids]
            column[key] = (spots[0] + spots[-1]) / 2
        return column[key]

    place(record.dataset)

    # The erased dataset's box gives the instant only; the full tombstone
    # sentence is printed above the diagram and would overrun a box.
    at = record.tombstone.at.isoformat() if record.tombstone.at else "no erasure instant"
    root_label = f"erased — {at}"
    labels = [root_label, *(_state(d) for d in descendants)]
    box_w = 16 + max(
        *(pdfmetrics.stringWidth(name, BOLD, 7) for name in [record.dataset, *column]),
        *(pdfmetrics.stringWidth(label, FONT, 6.5) for label in labels),
    )
    box_h, gap_x, gap_y = 30, 14, 26
    rows = 1 + max((d.depth for d in descendants), default=0)
    width = next_leaf[0] * box_w + (next_leaf[0] - 1) * gap_x
    height = rows * box_h + (rows - 1) * gap_y

    def origin(key: str, depth: int) -> tuple[float, float]:
        x = column[key] * (box_w + gap_x)
        y = height - (depth + 1) * box_h - depth * gap_y
        return x, y

    group = Group()
    by_key = {d.dataset: d for d in descendants}
    for d in descendants:
        parent = d.parent or record.dataset
        depth = by_key[parent].depth if parent in by_key else 0
        px, py = origin(parent, depth)
        cx, cy = origin(d.dataset, d.depth)
        group.add(
            Line(px + box_w / 2, py, cx + box_w / 2, cy + box_h, strokeColor=MUTED, strokeWidth=0.6)
        )
        if d.through:
            group.add(
                String(
                    (px + cx) / 2 + box_w / 2 + 3,
                    (py + cy + box_h) / 2 - 2,
                    d.through,
                    fontName=FONT,
                    fontSize=5.5,
                    fillColor=MUTED,
                )
            )

    def box(key: str, depth: int, label: str, *, tint: Any, heavy: bool) -> None:
        x, y = origin(key, depth)
        group.add(
            Rect(
                x,
                y,
                box_w,
                box_h,
                fillColor=tint,
                strokeColor=INK,
                strokeWidth=1.2 if heavy else 0.6,
            )
        )
        group.add(String(x + 8, y + box_h - 12, key, fontName=BOLD, fontSize=7, fillColor=INK))
        group.add(String(x + 8, y + 7, label, fontName=FONT, fontSize=6.5, fillColor=MUTED))

    box(record.dataset, 0, root_label, tint=colors.white, heavy=True)
    for d in descendants:
        box(
            d.dataset,
            d.depth,
            _state(d),
            tint=colors.white if d.reached else UNREACHED,
            heavy=False,
        )

    scale = min(1.0, WIDTH / width) if width else 1.0
    drawing = Drawing(width * scale, height * scale)
    group.scale(scale, scale)
    drawing.add(group)
    return drawing


def erasure_document(record: Any) -> bytes:
    """An erasure record as PDF bytes."""
    from .render import _how_text, _reached_text

    body: list[Flowable] = [_p(f"Erasure of {record.dataset}", TITLE), Spacer(1, 8)]
    body += _verdict(record, record.tombstone.earned())
    body += [Spacer(1, 8), _p(f"Tombstone: {record.tombstone.describe()}")]

    if record.descendants:
        body += [
            _p("What descends from it, and whether the erasure reached it", HEADING),
            KeepTogether([_tree(record)]),
            Spacer(1, 4),
        ]
        if any(not d.reached for d in record.descendants):
            body.append(
                _p(
                    "Tinted boxes are the places the proof does not reach. Each box also says "
                    "its state in words; the tint adds nothing the label does not.",
                    SMALL,
                )
            )
        body.append(_p("Descendants", HEADING))
        # The job goes under the dataset rather than in a column of its own: the
        # diagram names it on the edge as well, and a fourth column broke both
        # names mid-word on an A4 page.
        rows = [
            [_p(h, CELL) for h in ("Descendant, and the job that derived it", "Depth", "State")]
        ]
        for d in record.descendants:
            how = _how_text(d)
            state = _reached_text(d) + (f" — {how}" if how else "")
            rows.append(
                [
                    [_p(d.dataset, CELL), _p(f"derived by {d.through or 'unreported'}", SMALL)],
                    _p(str(d.depth), CELL),
                    _p(state, CELL),
                ]
            )
        table = Table(rows, colWidths=[82 * mm, 14 * mm, WIDTH - 96 * mm], repeatRows=1)
        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
        ]
        style += [
            ("BACKGROUND", (0, i), (-1, i), UNREACHED)
            for i, d in enumerate(record.descendants, start=1)
            if not d.reached
        ]
        table.setStyle(TableStyle(style))
        body.append(table)
    else:
        body += [Spacer(1, 6), _p("Nothing in the window read it — no descendants were found.")]

    body += _scope(record.scope)
    return _document(
        f"Erasure of {record.dataset}",
        body,
        footer=f"qedro {__version__} — erasure of {record.dataset}",
    )
