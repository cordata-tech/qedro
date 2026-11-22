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
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any
from xml.sax.saxutils import escape

import reportlab
from reportlab.graphics.shapes import (
    Circle,
    Drawing,
    Ellipse,
    Group,
    Line,
    Polygon,
    PolyLine,
    Rect,
    String,
)
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
from .stack import RUNNER_KINDS, STORAGE_KINDS

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


def _key(key: str, width: float, style: ParagraphStyle = CELL) -> Paragraph:
    """A dataset key, broken after a `/` rather than mid-word when it is too wide.

    A key has no spaces, so reportlab would otherwise split it wherever the
    column ends — `transactions_sc` / `ored` — and a reader checking a name
    against the catalog is the reader that cannot afford that.
    """
    usable = width - 12  # the cell's own padding
    if pdfmetrics.stringWidth(key, style.fontName, style.fontSize) <= usable:
        return _p(key, style)
    cut = key.rfind("/", 0, len(key) - 1)
    while (
        cut > 0 and pdfmetrics.stringWidth(key[: cut + 1], style.fontName, style.fontSize) > usable
    ):
        cut = key.rfind("/", 0, cut)
    if cut <= 0:
        return _p(key, style)
    return Paragraph(f"{escape(key[: cut + 1])}<br/>{escape(key[cut + 1 :])}", style)


class _Mark(Flowable):
    """The tombstone, drawn: Vera has no glyph for U+220E."""

    def __init__(self, size: float = 7.5) -> None:
        super().__init__()
        self.size = size
        self.width = self.height = size

    def draw(self) -> None:
        self.canv.setFillColor(INK)
        self.canv.rect(0, 0, self.size, self.size, stroke=0, fill=1)


def _wordmark_width(size: float) -> float:
    # The proportions of the SVG: a square 0.64 em on a side, 0.09 em after the R.
    return pdfmetrics.stringWidth("QEDR", BOLD, size) + 0.73 * size


def _draw_wordmark(canvas: Any, x: float, y: float, size: float, complete: bool) -> None:
    """QEDR and the square, as `docs/wordmark.svg` draws it, standing on *y*.

    The square is filled only on a record that earns the mark, and drawn as an
    outline on one that withholds it. The wordmark is the product's name finished
    by a complete run, so a filled square on a record that says it is not a
    proof would contradict the verdict printed under it.
    """
    canvas.saveState()
    canvas.setFillColor(INK)
    canvas.setStrokeColor(INK)
    canvas.setFont(BOLD, size)
    canvas.drawString(x, y, "QEDR")
    left, side = x + pdfmetrics.stringWidth("QEDR", BOLD, size) + 0.09 * size, 0.64 * size
    if complete:
        canvas.rect(left, y, side, side, stroke=0, fill=1)
    else:
        inset = size / 24  # half the line, so the outline covers the same square
        canvas.setLineWidth(2 * inset)
        canvas.rect(left + inset, y + inset, side - 2 * inset, side - 2 * inset, stroke=1, fill=0)
    canvas.restoreState()


class _Wordmark(Flowable):
    """The wordmark at the top of page one, as at the top of the README."""

    SIZE = 14

    def __init__(self, complete: bool) -> None:
        super().__init__()
        self.complete = complete
        self.width = _wordmark_width(self.SIZE)
        self.height = self.SIZE

    def draw(self) -> None:
        _draw_wordmark(self.canv, 0, 0, self.SIZE, self.complete)


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
        return [row, *_signoff(record)]
    out: list[Flowable] = [_p("This record does not claim to be a proof:", VERDICT)]
    out += [_p(f"• {reason}") for reason in record.completeness.reasons]
    return out + _signoff(record)


def _signoff(record: Any) -> list[Flowable]:
    """The sign-off under the verdict, when `--signoff` attached one (#40)."""
    standing = getattr(record, "signoff", None)
    if standing is None:
        return []
    return [
        Spacer(1, 4),
        _p(f"Sign-off: {standing.describe()}"),
        _p(f"A sign-off is {standing.CAVEAT}.", SMALL),
    ]


def _scope(
    scope: Any, title: str = "Scope of this record", extra: Sequence[tuple[str, str]] = ()
) -> list[Flowable]:
    """The scope statement, unconditionally, as every format prints it (#3)."""
    rows = [("Source", scope.source or "unknown"), ("Window", scope.window())]
    rows += [(label[0].upper() + label[1:], value) for label, value in scope.statement()]
    rows += extra
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
    # Kept together where it fits: the sentence saying what the record cannot
    # see belongs on the same page as what it did, not split by a page footer.
    return [KeepTogether([_p(title, HEADING), table, Spacer(1, 6), _p(scope.OUT_OF_VIEW, SMALL)])]


def _document(title: str, body: Sequence[Flowable], *, footer: str, complete: bool) -> bytes:
    buffer = io.BytesIO()
    body = [_Wordmark(complete), Spacer(1, 10), *body]

    def page(canvas: Any, doc: Any) -> None:
        # The wordmark again on every page, small, because printed pages get
        # separated: page four on its own still says what made it and whether
        # the record it came from claims to be a proof.
        _draw_wordmark(canvas, 20 * mm, 12 * mm, 7, complete)
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm + _wordmark_width(7) + 4, 12 * mm, f"{__version__} — {footer}")
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


@dataclass(frozen=True)
class _Node:
    """One box in a tree diagram: a dataset, and what the record says about it."""

    key: str
    depth: int
    lines: tuple[str, ...]
    parent: str = ""
    #: Where the proof does not reach. Tinted, and always said in `lines` too.
    gap: bool = False
    #: The tree's root, drawn with a heavier border.
    root: bool = False
    #: What labels the edge from the parent, such as the job that derived it.
    edge: str = ""
    #: The last line, what ran the step and where its data lives (#39), drawn
    #: in its own colour so it reads as a different kind of fact from the state.
    platform: str = ""
    #: The kinds `stack.KINDS` gives, drawn as icons: where the data lives
    #: beside the dataset's name, and what ran the step beside `platform`.
    stored_kind: str = ""
    ran_kind: str = ""


#: The platform line's colour: apart from the state's grey and the tint's
#: amber, so where a step ran is never read as how far the erasure got.
ACCENT = colors.HexColor("#2F5D8A")
ICON = 7.5
PLATFORM = ParagraphStyle("platform", parent=SMALL, textColor=ACCENT)


def _icon(kind: str, x: float, y: float, size: float = ICON, color: Any = INK) -> Group:
    """A small drawing for one kind of storage or step, standing on (*x*, *y*).

    Drawn here from lines and shapes, as the mark is, so there is nothing to
    license and nothing that fails to render. An icon stands for a kind, never
    for a vendor: Snowflake and PostgreSQL are both a database.
    """
    s, g = size, Group()
    line = {"strokeColor": color, "strokeWidth": 0.6}
    if kind == "database":
        # A cylinder: the body, its two sides, and the ellipses top and bottom.
        g.add(Ellipse(x + s / 2, y + s * 0.15, s / 2, s * 0.15, fillColor=colors.white, **line))
        g.add(Rect(x, y + s * 0.15, s, s * 0.7, fillColor=colors.white, strokeColor=None))
        g.add(Line(x, y + s * 0.15, x, y + s * 0.85, **line))
        g.add(Line(x + s, y + s * 0.15, x + s, y + s * 0.85, **line))
        g.add(Ellipse(x + s / 2, y + s * 0.85, s / 2, s * 0.15, fillColor=colors.white, **line))
    elif kind == "object storage":
        # A bucket: narrower at the bottom, open ellipse at the top.
        g.add(
            Polygon(
                [x, y + s * 0.8, x + s, y + s * 0.8, x + s * 0.82, y, x + s * 0.18, y],
                fillColor=colors.white,
                **line,
            )
        )
        g.add(Ellipse(x + s / 2, y + s * 0.8, s / 2, s * 0.14, fillColor=colors.white, **line))
    elif kind == "files":
        # A folder with its tab.
        g.add(
            Polygon(
                [
                    x, y, x + s, y, x + s, y + s * 0.7, x + s * 0.45, y + s * 0.7,
                    x + s * 0.35, y + s * 0.85, x, y + s * 0.85,
                ],
                fillColor=colors.white,
                **line,
            )
        )  # fmt: skip
    elif kind == "stream":
        # Three lines running into an arrowhead.
        for i in range(3):
            g.add(Line(x, y + s * (0.2 + 0.3 * i), x + s * 0.7, y + s * (0.2 + 0.3 * i), **line))
        g.add(
            Polygon(
                [x + s * 0.65, y + s * 0.05, x + s, y + s * 0.5, x + s * 0.65, y + s * 0.95],
                fillColor=None,
                **line,
            )
        )
    elif kind == "transformation":
        # Two chevrons: data going in one shape and out another.
        for dx in (0.0, 0.42):
            g.add(
                PolyLine(
                    [
                        x + s * dx,
                        y + s * 0.9,
                        x + s * (dx + 0.4),
                        y + s / 2,
                        x + s * dx,
                        y + s * 0.1,
                    ],
                    **line,
                )
            )
    elif kind == "orchestrator":
        # A small graph: one task fanning out to two.
        r = s * 0.14
        for cx, cy in ((0.15, 0.5), (0.85, 0.85), (0.85, 0.15)):
            g.add(Circle(x + s * cx, y + s * cy, r, fillColor=color, strokeColor=None))
        g.add(Line(x + s * 0.15, y + s * 0.5, x + s * 0.85, y + s * 0.85, **line))
        g.add(Line(x + s * 0.15, y + s * 0.5, x + s * 0.85, y + s * 0.15, **line))
    elif kind == "processing engine":
        # A gear: a ring with teeth.
        cx, cy = x + s / 2, y + s / 2
        for i in range(8):
            angle = math.pi * i / 4
            g.add(
                Line(
                    cx + math.cos(angle) * s * 0.3,
                    cy + math.sin(angle) * s * 0.3,
                    cx + math.cos(angle) * s * 0.5,
                    cy + math.sin(angle) * s * 0.5,
                    strokeColor=color,
                    strokeWidth=1.1,
                )
            )
        g.add(Circle(cx, cy, s * 0.32, fillColor=colors.white, **line))
        g.add(Circle(cx, cy, s * 0.12, fillColor=None, **line))
    elif kind == "data quality":
        # A tick in a circle.
        g.add(Circle(x + s / 2, y + s / 2, s / 2, fillColor=None, **line))
        g.add(
            PolyLine(
                [x + s * 0.25, y + s * 0.5, x + s * 0.43, y + s * 0.3, x + s * 0.75, y + s * 0.72],
                **line,
            )
        )
    return g


def _tree(nodes: Sequence[_Node]) -> Drawing:
    """A tree of boxes, root at the top, one row per depth.

    A tidy layout of the simplest kind: leaves take columns in the order given,
    a parent sits over the middle of its children, and depth is the row. Scaled
    down to the page width when the tree is wide, never up. Shared by every
    projection whose record is a tree, so they draw alike.
    """
    root = next(n for n in nodes if n.root)
    children: dict[str, list[_Node]] = {}
    for n in nodes:
        if not n.root:
            children.setdefault(n.parent or root.key, []).append(n)

    column: dict[str, float] = {}
    next_leaf = [0.0]

    def place(key: str) -> float:
        kids = children.get(key, [])
        if not kids:
            column[key] = next_leaf[0]
            next_leaf[0] += 1
        else:
            spots = [place(k.key) for k in kids]
            column[key] = (spots[0] + spots[-1]) / 2
        return column[key]

    place(root.key)
    placed = [n for n in nodes if n.key in column]

    # Room for an icon before the name and before the platform line, in every
    # box or in none, so the text of neighbouring boxes lines up.
    name_pad = ICON + 3 if any(n.stored_kind for n in placed) else 0
    platform_pad = ICON + 3 if any(n.ran_kind for n in placed) else 0
    box_w = 16 + max(
        max(
            [pdfmetrics.stringWidth(n.lines[0], BOLD, 7) + name_pad]
            + [pdfmetrics.stringWidth(line, FONT, 6.5) for line in n.lines[1:]]
            + [pdfmetrics.stringWidth(n.platform, FONT, 6.5) + platform_pad if n.platform else 0]
        )
        for n in placed
    )
    line_count = max(len(n.lines) + bool(n.platform) for n in placed)
    box_h, gap_x, gap_y = 12 + 9 * line_count, 14, 30
    rows = 1 + max(n.depth for n in placed)
    width = next_leaf[0] * box_w + (next_leaf[0] - 1) * gap_x
    height = rows * box_h + (rows - 1) * gap_y

    def origin(n: _Node) -> tuple[float, float]:
        x = column[n.key] * (box_w + gap_x)
        y = height - (n.depth + 1) * box_h - n.depth * gap_y
        return x, y

    group = Group()
    by_key = {n.key: n for n in placed}
    labels = Group()
    for n in placed:
        if n.root:
            continue
        px, py = origin(by_key[n.parent or root.key])
        cx, cy = origin(n)
        group.add(
            Line(px + box_w / 2, py, cx + box_w / 2, cy + box_h, strokeColor=MUTED, strokeWidth=0.6)
        )
        if n.edge:
            # On a white backing at the middle of its line, so the line never
            # runs through the job's name.
            w = pdfmetrics.stringWidth(n.edge, FONT, 5.5)
            mx = (px + cx) / 2 + box_w / 2
            my = (py + cy + box_h) / 2
            labels.add(
                Rect(mx - w / 2 - 2, my - 3, w + 4, 7.5, fillColor=colors.white, strokeColor=None)
            )
            labels.add(
                String(
                    mx,
                    my - 1,
                    n.edge,
                    fontName=FONT,
                    fontSize=5.5,
                    fillColor=MUTED,
                    textAnchor="middle",
                )
            )
    group.add(labels)

    for n in placed:
        x, y = origin(n)
        group.add(
            Rect(
                x,
                y,
                box_w,
                box_h,
                fillColor=UNREACHED if n.gap else colors.white,
                strokeColor=INK,
                strokeWidth=1.2 if n.root else 0.6,
            )
        )
        top = y + box_h - 12
        if n.stored_kind:
            group.add(_icon(n.stored_kind, x + 8, top - 1))
        for i, line in enumerate(n.lines):
            group.add(
                String(
                    x + 8 + (name_pad if i == 0 else 0),
                    top - 9 * i,
                    line,
                    fontName=BOLD if i == 0 else FONT,
                    fontSize=7 if i == 0 else 6.5,
                    fillColor=INK if i == 0 else MUTED,
                )
            )
        if n.platform:
            py_ = top - 9 * len(n.lines)
            if n.ran_kind:
                group.add(_icon(n.ran_kind, x + 8, py_ - 1, color=ACCENT))
            group.add(
                String(
                    x + 8 + (platform_pad if n.ran_kind else 0),
                    py_,
                    n.platform,
                    fontName=FONT,
                    fontSize=6.5,
                    fillColor=ACCENT,
                )
            )

    scale = min(1.0, WIDTH / width) if width else 1.0
    drawing = Drawing(width * scale, height * scale)
    group.scale(scale, scale)
    drawing.add(group)
    return drawing


def _legend(nodes: Sequence[_Node]) -> Drawing | None:
    """What each icon in the tree means, in words, for the kinds it uses.

    The words come first everywhere else in these documents, and an icon is
    no exception: a reader who does not know the gear should not have to guess.
    """
    used = {n.stored_kind for n in nodes} | {n.ran_kind for n in nodes}
    kinds = [k for k in (*STORAGE_KINDS, *RUNNER_KINDS) if k in used]
    if not kinds:
        return None
    group, x = Group(), 0.0
    for kind in kinds:
        color = ACCENT if kind in RUNNER_KINDS else INK
        group.add(_icon(kind, x, 0, color=color))
        group.add(String(x + ICON + 3, 1, kind, fontName=FONT, fontSize=6.5, fillColor=MUTED))
        x += ICON + 3 + pdfmetrics.stringWidth(kind, FONT, 6.5) + 12
    # Room under the baseline for descenders: `object storage` has a g and a y.
    group.translate(0, 2.5)
    drawing = Drawing(min(x, WIDTH), ICON + 4)
    drawing.add(group)
    return drawing


def _with_notes(nodes: Sequence[_Node], *, edges: str, tinted: str) -> list[Flowable]:
    """The tree, the legend for its icons, and what its lines and tint mean.

    The tint note appears only where a box is tinted, and the legend only lists
    the icons the tree uses.
    """
    out: list[Flowable] = [_tree(nodes), Spacer(1, 6)]
    if legend := _legend(nodes):
        out += [legend, Spacer(1, 4)]
    notes = [edges]
    if any(n.platform for n in nodes):
        notes.append(
            "The coloured line in each box says what ran the step and where its data lives, "
            "as the events report it."
        )
    if any(n.gap for n in nodes):
        notes.append(tinted)
    return out + [_p(" ".join(notes), SMALL)]


def _stack_line(described: str) -> str:
    """Where a step ran, for a box or a cell, or that the events did not say (#39)."""
    return f"on {described}" if described else "platform not reported"


def _erasure_nodes(record: Any) -> list[_Node]:
    # The erased dataset's box gives the instant only; the full tombstone
    # sentence is printed above the diagram and would overrun a box.
    at = record.tombstone.at.isoformat() if record.tombstone.at else "no erasure instant"
    nodes = [
        _Node(
            record.dataset,
            0,
            (record.dataset, f"erased — {at}"),
            root=True,
            platform=_stack_line(record.stored_in),
            stored_kind=record.stored_in_kind,
        )
    ]
    nodes += [
        _Node(
            d.dataset,
            d.depth,
            (d.dataset, _state(d)),
            parent=d.parent or record.dataset,
            gap=not d.reached,
            edge=d.through,
            platform=_stack_line(d.stack.describe()),
            stored_kind=d.stack.stored_in_kind,
            ran_kind=d.stack.ran_on_kind,
        )
        for d in record.descendants
    ]
    return nodes


def erasure_document(record: Any) -> bytes:
    """An erasure record as PDF bytes."""
    from .render import _how_text, _reached_text

    body: list[Flowable] = [_p(f"Erasure of {record.dataset}", TITLE), Spacer(1, 8)]
    body += _verdict(record, record.tombstone.earned())
    body += [Spacer(1, 8), _p(f"Tombstone: {record.tombstone.describe()}")]

    if record.descendants:
        body += [
            _p("What descends from it, and whether the erasure reached it", HEADING),
            KeepTogether(
                _with_notes(
                    _erasure_nodes(record),
                    edges="Each line is labelled with the job that read the dataset above it "
                    "and wrote the one below.",
                    tinted="Tinted boxes are the places the proof does not reach. Each box "
                    "also says its state in words; the tint adds nothing the label does not.",
                )
            ),
        ]
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
                    [
                        _key(d.dataset, 82 * mm),
                        _p(f"derived by {d.through or 'unreported'}", SMALL),
                        _p(_stack_line(d.stack.describe()), PLATFORM),
                    ],
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
        footer=f"erasure of {record.dataset}",
        complete=record.complete,
    )


# --- provenance --------------------------------------------------------------


def _signature_word(production: Any) -> str:
    """The signature in two or three words, for a box; the table has the sentence."""
    if production.signature.signed is True:
        return "signed"
    if production.signature.signed is False:
        return "not signed"
    if production.signature.without_commit:
        return "verdict without a commit"
    return "signature unknown"


def _provenance_nodes(record: Any) -> list[_Node]:
    """The chain as boxes, the published dataset at the top and its sources below.

    The walk is breadth-first, so the steps one level up are not necessarily
    in order with their children: a step hangs under the step one level up
    whose run read it, and under the last step one level up only when no run
    says it read it.
    """
    nodes: list[_Node] = []
    last: dict[int, str] = {}
    read_by: dict[tuple[int, str], str] = {}
    for step in record.steps:
        if step.production is not None:
            for read in step.production.reads:
                read_by.setdefault((step.depth, read), step.dataset)
    for step in record.steps:
        p = step.production
        if p is None:
            lines = (step.dataset, step.ended or "nothing in the window produced it")
            gap = False
        else:
            commit = f"at {p.code.short}" if p.code.commit else "no commit named"
            lines = (step.dataset, f"{p.job}, {commit}", _signature_word(p))
            # The gaps the chain withholds its mark for: a step that cannot show
            # a signed commit. An ending is stated, not tinted, because a source
            # and a producer outside the window look the same from here.
            gap = not p.authorised
        nodes.append(
            _Node(
                step.dataset,
                step.depth,
                lines,
                parent=read_by.get((step.depth - 1, step.dataset), last.get(step.depth - 1, "")),
                gap=gap,
                root=step.depth == 0,
                platform=_stack_line(p.stack.describe()) if p else "",
                stored_kind=p.stack.stored_in_kind if p else "",
                ran_kind=p.stack.ran_on_kind if p else "",
            )
        )
        last[step.depth] = step.dataset
    return nodes


def provenance_document(record: Any) -> bytes:
    """A provenance chain as PDF bytes."""
    body: list[Flowable] = [_p(f"Provenance of {record.dataset}", TITLE), Spacer(1, 8)]
    body += _verdict(record, "every step ran under a signed commit")

    if record.steps:
        body += [
            _p("From the published dataset back to what it was made from", HEADING),
            KeepTogether(
                _with_notes(
                    _provenance_nodes(record),
                    edges="Each line joins a dataset to one that its producing run read.",
                    tinted="Tinted boxes are steps that cannot show a signed commit. Each box "
                    "also says why in words; the tint adds nothing the label does not.",
                )
            ),
        ]
        body.append(_p("Steps", HEADING))
        rows = [[_p(h, CELL) for h in ("Step", "Depth", "Evidence")]]
        for step in record.steps:
            p = step.production
            if p is None:
                evidence = [_p(step.ended or "nothing in the window produced it", CELL)]
            else:
                when = p.when.isoformat() if p.when else "no time reported"
                lines = [
                    f"produced by {p.job}",
                    f"run {p.run_id or 'unreported'} ({p.event_type.lower()}), {when}",
                    f"code: {p.code.describe()}",
                    f"signature: {p.signature.describe()}",
                    f"source: {p.published.describe()}",
                    f"platform: {p.stack.describe() or 'not reported'}",
                ]
                if step.also_produced_by:
                    n = step.also_produced_by
                    lines.append(f"also: {n} other {'run' if n == 1 else 'runs'} wrote this")
                evidence = [_p(line, CELL) for line in lines]
            rows.append([_key(step.dataset, 72 * mm), _p(str(step.depth), CELL), evidence])
        table = Table(rows, colWidths=[72 * mm, 14 * mm, WIDTH - 86 * mm], repeatRows=1)
        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
        ]
        style += [
            ("BACKGROUND", (0, i), (-1, i), UNREACHED)
            for i, step in enumerate(record.steps, start=1)
            if step.production is not None and not step.production.authorised
        ]
        table.setStyle(TableStyle(style))
        body.append(table)

    body += _scope(record.scope, title="Scope of this chain")
    return _document(
        f"Provenance of {record.dataset}",
        body,
        footer=f"provenance of {record.dataset}",
        complete=record.complete,
    )


# --- the Art. 30 record --------------------------------------------------------

#: Item, value, and where the value came from. The source column is what makes
#: this a record rather than a register: a register states, this says on what.
ITEM_W, SOURCE_W = 48 * mm, 40 * mm
VALUE_W = WIDTH - ITEM_W - SOURCE_W


@dataclass(frozen=True)
class _Row:
    """One line of an activity's table."""

    label: str
    value: str
    source: str
    #: The Art. 30(1) item it answers, cited under the label.
    item: str = ""
    #: Part of why the record does not claim to be a proof. Tinted, and the
    #: source column says why in words.
    gap: bool = False
    #: Dataset keys, one per line, each kept whole.
    keys: tuple[str, ...] = ()
    #: Where the value came from, in qedro's sentences (#48), printed as
    #: numbered footnotes under the table. One per value for classification.
    why: tuple[str, ...] = ()


#: The classification rows, in Art. 30(1) order: the tag key, its label here,
#: and the item it answers.
CLASSIFICATION_ROWS = (
    ("data_category", "Categories of personal data", "c"),
    ("special_category", "Special categories", "c"),
    ("subject_type", "Categories of data subjects", "c"),
    ("residency", "Residency", "e"),
    ("retention", "Retention", "f"),
)


def _sourced_row(label: str, sourced: Any, item: str = "") -> _Row:
    from .xlsx import _source

    return _Row(
        label,
        sourced.value or "—",
        _source(sourced) if sourced.value else "nothing declared",
        item=item,
        gap=not sourced.evidenced or sourced.unrecognised,
    )


def _asserted_row(label: str, values: tuple[str, ...], item: str) -> _Row:
    # Art. 30(1)(d) and (g): nothing emits either, so a value is always somebody's
    # word, and says so in the column beside it.
    if not values:
        return _Row(label, "—", "nothing declared", item=item)
    return _Row(label, "; ".join(values), "declared", item=item)


def _plain(text: str) -> str:
    """qedro's sentence with its backticks dropped: on paper a name reads as itself."""
    return text.replace("`", "")


def _explained(rows: list[_Row], whys: Mapping[str, tuple[str, ...]]) -> list[_Row]:
    """Each row with the sentences explaining it, matched by label."""
    return [replace(r, why=whys.get(r.label, ())) for r in rows]


def _activity_whys(record: Any, activity: Any) -> dict[str, tuple[str, ...]]:
    from . import explain

    refs, vocab = record.references, record.vocabulary
    whys: dict[str, tuple[str, ...]] = {
        label: (
            _plain(
                explain.activity_value(
                    activity, name, getattr(activity, name), references=refs, vocabulary=vocab
                ).text
            ),
        )
        for label, name in (("Purpose", "purpose"), ("Legal basis", "legal_basis"))
    }
    whys |= {
        label: (
            _plain(
                explain.activity_list(activity, name, getattr(activity, name), references=refs).text
            ),
        )
        for label, name in (
            ("Recipients", "recipients"),
            ("Security measures", "security_measures"),
        )
    }
    for key, label, _ in CLASSIFICATION_ROWS:
        whys[label] = tuple(
            _plain(explain.classification(activity, c, references=refs, vocabulary=vocab).text)
            for c in activity.classification
            if c.key == key
        )
    return whys


def _declared_whys(record: Any, entry: Any) -> dict[str, tuple[str, ...]]:
    from . import explain

    refs, vocab = record.references, record.vocabulary
    whys: dict[str, tuple[str, ...]] = {
        label: (
            _plain(
                explain.declared_value(
                    entry, name, getattr(entry, name), references=refs, vocabulary=vocab
                ).text
            ),
        )
        for label, name in (("Purpose", "purpose"), ("Legal basis", "legal_basis"))
    }
    return whys | {
        label: (
            _plain(explain.declared_list(entry, name, getattr(entry, name), references=refs).text),
        )
        for label, name in (
            ("Recipients", "recipients"),
            ("Security measures", "security_measures"),
        )
    }


def _activity_rows(activity: Any) -> list[_Row]:
    from .xlsx import SOURCE

    rows = [
        _sourced_row("Purpose", activity.purpose, "b"),
        _sourced_row("Legal basis", activity.legal_basis),
    ]
    for key, label, item in CLASSIFICATION_ROWS:
        found = [c for c in activity.classification if c.key == key]
        if not found:
            # Nothing reported, which is not the same as nothing applies: a dash
            # alone would read as *no special categories here*.
            rows.append(_Row(label, "—", "nothing reported", item=item))
            continue
        by = sorted({j for c in found for j in c.declared_by})
        source = SOURCE.get(str(found[0].provenance), str(found[0].provenance))
        if by:
            source += f", declared by {', '.join(by)}"
        flagged = [c.value for c in found if c.unrecognised]
        if flagged:
            source += f" — {', '.join(flagged)} not in the vocabulary"
        rows.append(
            _Row(label, ", ".join(c.value for c in found), source, item=item, gap=bool(flagged))
        )
    rows.append(_asserted_row("Recipients", activity.recipients, "d"))
    rows.append(_asserted_row("Security measures", activity.security_measures, "g"))
    if activity.unclassified:
        total = len(set(activity.inputs) | set(activity.outputs))
        rows.append(
            _Row(
                "Unclassified",
                f"{len(activity.unclassified)} of {total}",
                "no classification the record can use",
                keys=activity.unclassified,
            )
        )
    if activity.inputs:
        rows.append(_Row("Reads", "", "lineage", keys=activity.inputs))
    if activity.outputs:
        rows.append(_Row("Writes", "", "lineage", keys=activity.outputs))
    first = activity.first_seen.isoformat() if activity.first_seen else "unreported"
    last = activity.last_seen.isoformat() if activity.last_seen else "unreported"
    rows.append(
        _Row("Runs", f"{activity.runs} in the window, first {first}, last {last}", "lineage")
    )
    return rows


def _declared_rows(entry: Any) -> list[_Row]:
    # Every row the events would have filled says `no lineage`: a dash would read
    # as *nothing applies* rather than *nothing could have said*.
    rows = [
        _sourced_row("Purpose", entry.purpose, "b"),
        _sourced_row("Legal basis", entry.legal_basis),
    ]
    rows += [_Row(label, "no lineage", "—", item=item) for _, label, item in CLASSIFICATION_ROWS]
    rows.append(_asserted_row("Recipients", entry.recipients, "d"))
    rows.append(_asserted_row("Security measures", entry.security_measures, "g"))
    if entry.inputs:
        rows.append(_Row("Reads", "no lineage — declared:", "declared", keys=entry.inputs))
    else:
        rows.append(_Row("Reads", "no lineage", "—"))
    rows += [_Row("Writes", "no lineage", "—"), _Row("Runs", "no lineage", "—")]
    if entry.note:
        rows.append(_Row("Note", entry.note, "declared"))
    return rows


def _activity_table(rows: Sequence[_Row]) -> list[Flowable]:
    """The table, then its footnotes: the sentences saying where each value came
    from (#48), numbered from 1 under each activity so a note sits on the same
    page as the row that cites it."""
    cells = []
    notes: list[str] = []
    for r in rows:
        label: list[Flowable] = [_p(r.label, CELL)]
        if r.item:
            label.append(_p(f"Art. 30(1)({r.item})", SMALL))
        value: list[Flowable] = [_p(r.value, CELL)] if r.value else []
        value += [_key(k, VALUE_W) for k in r.keys]
        marks = []
        for why in r.why:
            notes.append(why)
            marks.append(f"[{len(notes)}]")
        source = f"{r.source} {' '.join(marks)}" if marks else r.source
        cells.append([label, value, _p(source, CELL)])
    table = Table(cells, colWidths=[ITEM_W, VALUE_W, SOURCE_W])
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
    ]
    style += [("BACKGROUND", (0, i), (-1, i), UNREACHED) for i, r in enumerate(rows) if r.gap]
    table.setStyle(TableStyle(style))
    footnotes = [_p(f"[{n}] {note}", SMALL) for n, note in enumerate(notes, start=1)]
    return [table, *([Spacer(1, 3)] if footnotes else []), *footnotes]


def _overview(record: Any) -> Table:
    """One line per activity, so a reader sees the whole record before any of it."""
    from .xlsx import _source

    widths = [58 * mm, 44 * mm, 38 * mm, WIDTH - 140 * mm]
    rows: list[list[Any]] = [
        [_p(h, CELL) for h in ("Activity", "Purpose", "Legal basis", "Purpose and basis from")]
    ]
    gaps: list[int] = []
    for a in record.activities:
        sources = {_source(a.purpose), _source(a.legal_basis)}
        rows.append(
            [
                _key(a.key, widths[0]),
                _p(a.purpose.value or "—", CELL),
                _p(a.legal_basis.value or "—", CELL),
                _p(" / ".join(sorted(sources)), CELL),
            ]
        )
        if not a.evidenced or a.purpose.unrecognised or a.legal_basis.unrecognised:
            gaps.append(len(rows) - 1)
    for d in record.declared:
        rows.append(
            [
                _key(d.name, widths[0]),
                _p(d.purpose.value or "—", CELL),
                _p(d.legal_basis.value or "—", CELL),
                _p("declared, no lineage", CELL),
            ]
        )
        gaps.append(len(rows) - 1)
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
    ]
    style += [("BACKGROUND", (0, i), (-1, i), UNREACHED) for i in gaps]
    table.setStyle(TableStyle(style))
    return table


def _requirements(record: Any) -> list[Flowable]:
    """The regulation's wording for every requirement the record answers, once,
    quoted rather than paraphrased (#48). From the references document, so a
    record mapped to another regulation quotes that one."""
    refs = record.references
    if not refs.by_id:
        return []
    body: list[Flowable] = [_p("What each field answers, in the regulation's words", HEADING)]
    if refs.regulation:
        body.append(_p(refs.regulation + (f" — {refs.source}" if refs.source else ""), SMALL))
    rows = [[_p(r.cite, CELL), _p(f"“{r.text}”", CELL)] for r in refs.by_id.values()]
    table = Table(rows, colWidths=[ITEM_W, WIDTH - ITEM_W])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
            ]
        )
    )
    return [*body, table]


def ropa_document(record: Any) -> bytes:
    """An Art. 30 record of processing activities as PDF bytes."""
    controller = record.controller
    body: list[Flowable] = [_p("Record of processing activities", TITLE), Spacer(1, 4)]
    # Art. 30(1)(a). A missing controller is said, not left blank: a blank reads
    # as a layout slip rather than as the hole it is.
    who = [("Controller", controller.name or "No controller is declared")]
    who += [
        (label, value)
        for label, value in (
            ("Contact", controller.contact),
            ("Representative", controller.representative),
            ("Data protection officer", controller.dpo),
        )
        if value
    ]
    people = Table(
        [[_p(label, SMALL), _p(value, BODY)] for label, value in who],
        colWidths=[ITEM_W, WIDTH - ITEM_W],
        hAlign="LEFT",
    )
    people.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                *[(side, (0, 0), (-1, -1), 1) for side in ("TOPPADDING", "BOTTOMPADDING")],
                ("LEFTPADDING", (0, 0), (0, -1), 0),
            ]
        )
    )
    body.append(people)
    from . import explain

    said = explain.controller(controller, references=record.references)
    cite = f" ({said.answers.cite})" if said.answers else ""
    body += [Spacer(1, 2), _p(_plain(said.text) + cite, SMALL), Spacer(1, 10)]
    body += _verdict(record, "every activity stands on emitted evidence")

    if record.activities or record.declared:
        body.append(_p("The activities", HEADING))
        body.append(_overview(record))
        if any(not a.evidenced for a in record.activities) or record.declared:
            body.append(Spacer(1, 4))
            body.append(
                _p(
                    "Tinted rows are part of why the record does not claim to be a proof. "
                    "Each also says why in words; the tint adds nothing the text does not.",
                    SMALL,
                )
            )
    else:
        body += [Spacer(1, 6), _p("No processing activity was found in the window.")]

    for activity in record.activities:
        heading = activity.key + (f" ({activity.domain})" if activity.domain else "")
        rows = _explained(_activity_rows(activity), _activity_whys(record, activity))
        body.append(KeepTogether([_p(heading, HEADING), *_activity_table(rows)]))
    for entry in record.declared:
        heading = f"{entry.name} — declared, no lineage"
        rows = _explained(_declared_rows(entry), _declared_whys(record, entry))
        body.append(KeepTogether([_p(heading, HEADING), *_activity_table(rows)]))
    body += _requirements(record)

    scope = record.scope
    extra = [("Vocabulary", record.vocabulary)] if record.vocabulary else []
    if scope.domains_source():
        extra.append(("Domains", scope.domains_source()))
    if scope.domains_silent:
        extra.append(("Silent", f"{', '.join(scope.domains_silent)} (in scope, no lineage)"))
    body += _scope(scope, extra=extra)
    name = controller.name or "no controller declared"
    return _document(
        f"Record of processing activities — {name}",
        body,
        footer=f"record of processing activities, {name}",
        complete=record.complete,
    )
