"""The Art. 30 record as a workbook.

The one output an auditor actually asks for, and the only one that is not text.
A DPO receives a spreadsheet, forwards it, and somebody eventually sorts and
filters it — which changes what this format has to do, not only how it looks.

**The verdict goes where the file opens.** A record that does not claim to be a
proof says so on the first sheet, above the table. Parking that behind the
activities, or on a tab nobody clicks, would reproduce the exact failure this
tool exists to prevent: an artefact whose holes are invisible. The Scope sheet
carries the reasons; the first sheet carries the verdict and points at them.

**Provenance is a column of words, never a colour.** The tint on an asserted
cell is reinforcement for a reader who can see it and carries nothing on its
own — every tinted cell also says ``mapping file`` or ``not declared`` in text.

Timestamps are written as ISO-8601 strings rather than as spreadsheet dates.
Excel's date type has no timezone and openpyxl refuses an aware datetime, so a
real date cell would mean dropping the offset from evidence whose whole value
is being exact about when something ran.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from . import TOMBSTONE
from .errors import QedroError
from .ropa import Activity, Record, Sourced

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ModuleNotFoundError as exc:
    # A declared dependency, so this means a broken install rather than a
    # choice — but a sentence still beats a traceback.
    raise QedroError(
        "xlsx output needs openpyxl, which installs with qedro — try "
        "`pip install openpyxl`, or ask for --format markdown"
    ) from exc

#: Column headings and the width each needs to be readable without the reader
#: dragging borders around.
COLUMNS: tuple[tuple[str, int], ...] = (
    ("Activity", 38),
    ("Domain", 14),
    ("Purpose", 24),
    ("Purpose source", 20),
    ("Legal basis", 22),
    ("Legal basis source", 20),
    ("Reads", 34),
    ("Writes", 34),
    ("Runs", 7),
    ("First seen", 26),
    ("Last seen", 26),
    ("Notes", 46),
)

AT = {heading: index for index, (heading, _) in enumerate(COLUMNS, start=1)}
WRAPPED = {AT["Reads"], AT["Writes"], AT["Notes"]}

#: How a provenance reads to somebody who did not write this tool.
SOURCE = {
    "facet": "emitted facet",
    "mapping": "mapping file",
    "absent": "not declared",
}

#: Past this many dataset keys a cell stops being readable, and a cell has a
#: hard character limit besides. What was dropped is stated in the cell: a list
#: that simply stops looks complete.
DATASETS_PER_CELL = 40

#: The table starts here. Above it: the title, the controller, the contact and
#: the verdict.
HEADER_ROW = 6

TITLE = Font(bold=True, size=14)
STRONG = Font(bold=True)
HEADING = Font(bold=True, color="FFFFFFFF")
HEADING_FILL = PatternFill(fill_type="solid", start_color="FF1F2933", end_color="FF1F2933")
ASSERTED_FILL = PatternFill(fill_type="solid", start_color="FFFDF0D5", end_color="FFFDF0D5")
TOP = Alignment(vertical="top")
WRAP = Alignment(vertical="top", wrap_text=True)


def workbook(record: Record) -> bytes:
    """The record as ``.xlsx`` bytes, ready to be written or handed on."""
    book = Workbook()
    # Document properties, because a file that leaves a DPO's outbox should say
    # what made it without anyone having to open it.
    book.properties.creator = "qedro"
    book.properties.title = "Record of processing activities"
    book.properties.description = record.scope.OUT_OF_VIEW

    _activities(book.active, record)
    _scope(book.create_sheet("Scope"), record)

    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _activities(sheet: Any, record: Record) -> None:
    sheet.title = "Art. 30 record"

    sheet["A1"] = "Record of processing activities"
    sheet["A1"].font = TITLE
    # Art. 30(1)(a). A blank here would read as a formatting slip rather than
    # as the hole it is.
    sheet["A2"] = record.controller.name or "No controller is declared"
    sheet["A2"].font = STRONG
    sheet["A3"] = f"Contact: {record.controller.contact}" if record.controller.contact else ""
    sheet["A4"] = _verdict(record)
    sheet["A4"].font = STRONG

    for index, (heading, width) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=HEADER_ROW, column=index, value=heading)
        cell.font = HEADING
        cell.fill = HEADING_FILL
        cell.alignment = WRAP
        sheet.column_dimensions[get_column_letter(index)].width = width

    for offset, activity in enumerate(record.activities):
        _row(sheet, HEADER_ROW + 1 + offset, activity)

    last_column = get_column_letter(len(COLUMNS))
    last_row = HEADER_ROW + len(record.activities)
    sheet.auto_filter.ref = f"A{HEADER_ROW}:{last_column}{last_row}"
    sheet.freeze_panes = f"A{HEADER_ROW + 1}"


def _row(sheet: Any, row: int, activity: Activity) -> None:
    values = (
        activity.key,
        activity.domain,
        activity.purpose.value or "—",
        _source(activity.purpose),
        activity.legal_basis.value or "—",
        _source(activity.legal_basis),
        _datasets(activity.inputs),
        _datasets(activity.outputs),
        activity.runs,
        _when(activity.first_seen),
        _when(activity.last_seen),
        "\n".join(activity.gaps()),
    )
    for index, value in enumerate(values, start=1):
        cell = sheet.cell(row=row, column=index, value=value)
        cell.alignment = WRAP if index in WRAPPED else TOP

    # One tint, meaning *this cell is part of why the record does not claim to
    # be a proof*. Which of the two problems it is comes from the text in the
    # cell and from the Notes column; the colour never carries it alone. The
    # source cell is tinted when the value is not evidence, and the value cell
    # when the vocabulary does not define it — an emitted value can be perfectly
    # good evidence of a term nobody agreed on.
    for value_column, source_column, sourced in (
        (AT["Purpose"], AT["Purpose source"], activity.purpose),
        (AT["Legal basis"], AT["Legal basis source"], activity.legal_basis),
    ):
        if not sourced.evidenced:
            sheet.cell(row=row, column=source_column).fill = ASSERTED_FILL
        if sourced.unrecognised:
            sheet.cell(row=row, column=value_column).fill = ASSERTED_FILL


def _verdict(record: Record) -> str:
    if record.complete:
        return f"Every activity in this record stands on emitted evidence. {TOMBSTONE}"
    count = len(record.completeness.reasons)
    noun = "reason" if count == 1 else "reasons"
    return f"This record does not claim to be a proof — {count} {noun} on the Scope sheet."


def _source(sourced: Sourced) -> str:
    """Where the value came from, and whether the vocabulary knows it.

    The flag sits on the source cell rather than on the value, so the value
    column stays exactly what was declared and a reader can still filter on it.
    """
    label = SOURCE.get(str(sourced.provenance), str(sourced.provenance))
    return f"{label} — not in the vocabulary" if sourced.unrecognised else label


def _datasets(keys: tuple[str, ...]) -> str:
    if len(keys) <= DATASETS_PER_CELL:
        return "\n".join(keys)
    remaining = len(keys) - DATASETS_PER_CELL
    return "\n".join((*keys[:DATASETS_PER_CELL], f"… and {remaining} more"))


def _when(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _scope(sheet: Any, record: Record) -> None:
    scope = record.scope
    sheet.column_dimensions["A"].width = 26
    sheet.column_dimensions["B"].width = 96

    sheet["A1"] = "Scope of this record"
    sheet["A1"].font = TITLE

    rows = [
        ("Source", scope.source or "unknown"),
        ("Window", scope.window()),
        ("In view", f"{scope.jobs} jobs, {scope.datasets} datasets, {scope.events} events"),
        ("Namespaces", ", ".join(scope.namespaces)),
        (
            "Provenance",
            (
                f"{scope.evidenced} evidenced, {scope.from_mapping} from the mapping file, "
                f"{scope.undeclared} undeclared"
            ),
        ),
        ("Vocabulary", record.vocabulary),
    ]
    if scope.domains_silent:
        rows.append(("Declared but silent", ", ".join(scope.domains_silent)))

    row = 3
    for label, value in rows:
        sheet.cell(row=row, column=1, value=label).font = STRONG
        sheet.cell(row=row, column=2, value=value).alignment = WRAP
        row += 1

    # Unconditional, on every run including one that earns the mark. See
    # cordata-tech/qedro#3.
    row += 1
    sheet.cell(row=row, column=1, value="Not covered").font = STRONG
    sheet.cell(row=row, column=2, value=scope.OUT_OF_VIEW).alignment = WRAP
    sheet.row_dimensions[row].height = 64

    row += 2
    sheet.cell(row=row, column=1, value="Completeness").font = STRONG
    if record.complete:
        sheet.cell(
            row=row,
            column=2,
            value=f"Every activity in this record stands on emitted evidence. {TOMBSTONE}",
        )
        return

    sheet.cell(row=row, column=2, value="This record does not claim to be a proof.").font = STRONG
    for reason in record.completeness.reasons:
        row += 1
        sheet.cell(row=row, column=2, value=reason).alignment = WRAP
