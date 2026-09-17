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

from . import TOMBSTONE, words
from .deployer import SIX_MONTHS, DeployerRecord
from .errors import QedroError
from .provenance import Record as ProvenanceRecord
from .quality import Record as QualityRecord
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
    "declared": "declared, no lineage",
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
    for offset, entry in enumerate(record.declared, start=len(record.activities)):
        _declared_row(sheet, HEADER_ROW + 1 + offset, entry)

    last_column = get_column_letter(len(COLUMNS))
    last_row = HEADER_ROW + len(record.activities) + len(record.declared)
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


def _declared_row(sheet: Any, row: int, entry: Any) -> None:
    """A declared activity. Every cell the events would have filled says
    `no lineage` — an empty Reads cell reads as *touches no data*, and a 0 in
    Runs as *ran zero times*, and neither is known."""
    reads = "no lineage"
    if entry.inputs:
        reads = "no lineage — declared:\n" + "\n".join(entry.inputs)
    values = (
        entry.name,
        entry.domain,
        entry.purpose.value or "—",
        _source(entry.purpose),
        entry.legal_basis.value or "—",
        _source(entry.legal_basis),
        reads,
        "no lineage",
        "no lineage",
        "no lineage",
        "no lineage",
        "\n".join(x for x in ("declared, no lineage", entry.note) if x),
    )
    for index, value in enumerate(values, start=1):
        cell = sheet.cell(row=row, column=index, value=value)
        cell.alignment = WRAP if index in WRAPPED else TOP
    for column in (AT["Purpose source"], AT["Legal basis source"]):
        sheet.cell(row=row, column=column).fill = ASSERTED_FILL


def _verdict(record: Record) -> str:
    if record.complete:
        return f"Every activity in this record stands on emitted evidence. {TOMBSTONE}"
    n = len(record.completeness.reasons)
    return (
        f"This record does not claim to be a proof — {words.count(n, 'reason')} on the Scope sheet."
    )


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

    # From `scope.lines()`, as the other projections' sheets already were. This
    # sheet listed its rows itself, which is how the declared count from #6 never
    # reached the workbook while every other format printed it.
    rows = [("Source", scope.source or "unknown"), ("Window", scope.window())]
    rows += [(label[0].upper() + label[1:], value) for label, value in scope.lines()]
    rows.append(("Vocabulary", record.vocabulary))
    if scope.domains_source():
        rows.append(("Domains", scope.domains_source()))
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


# --- the assertion history -------------------------------------------------

#: One row per expectation rather than per dataset. A reader filtering for
#: `FAILED` wants the expectation that failed, not the table it was on.
QUALITY_COLUMNS: tuple[tuple[str, int], ...] = (
    ("Dataset", 44),
    ("Domain", 14),
    ("Expectation", 40),
    ("Column", 20),
    ("Result", 12),
    ("Runs", 8),
    ("Failed", 8),
    ("Last failure", 26),
    ("Last asserted", 26),
    ("Asserted by", 34),
)

QUALITY_AT = {heading: index for index, (heading, _) in enumerate(QUALITY_COLUMNS, start=1)}


def quality_workbook(record: QualityRecord) -> bytes:
    """The assertion history as ``.xlsx`` bytes.

    Three sheets, and the middle one is the point. *Not checked* is a sheet of
    its own rather than a note at the bottom of the first, because a reader who
    stops after the green table has been misled — and a tab they have to
    dismiss is harder to stop at than a paragraph they can skim past.
    """
    book = Workbook()
    book.properties.creator = "qedro"
    book.properties.title = "Data quality assertion history"
    book.properties.description = record.scope.OUT_OF_VIEW

    _expectations(book.active, record)
    _unchecked(book.create_sheet("Not checked"), record)
    _quality_scope(book.create_sheet("Scope"), record)

    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _expectations(sheet: Any, record: QualityRecord) -> None:
    sheet.title = "Assertions"

    sheet["A1"] = "Data quality assertion history"
    sheet["A1"].font = TITLE
    sheet["A2"] = record.controller.name or "No controller is declared"
    sheet["A2"].font = STRONG
    sheet["A3"] = (
        f"{record.scope.checked} datasets checked, "
        f"{record.scope.unchecked} with no assertions at all"
    )
    sheet["A4"] = _quality_verdict(record)
    sheet["A4"].font = STRONG

    for index, (heading, width) in enumerate(QUALITY_COLUMNS, start=1):
        cell = sheet.cell(row=HEADER_ROW, column=index, value=heading)
        cell.font = HEADING
        cell.fill = HEADING_FILL
        cell.alignment = WRAP
        sheet.column_dimensions[get_column_letter(index)].width = width

    row = HEADER_ROW
    for dataset in record.datasets:
        for expectation in dataset.expectations:
            row += 1
            values = (
                dataset.key,
                dataset.domain,
                expectation.assertion,
                expectation.column,
                "held" if expectation.holds else "FAILED",
                expectation.runs,
                expectation.failures,
                _when(expectation.last_failure),
                _when(expectation.last_seen),
                ", ".join(dataset.asserted_by),
            )
            for index, value in enumerate(values, start=1):
                cell = sheet.cell(row=row, column=index, value=value)
                cell.alignment = TOP
            if not expectation.holds:
                sheet.cell(row=row, column=QUALITY_AT["Result"]).fill = ASSERTED_FILL

    sheet.auto_filter.ref = (
        f"A{HEADER_ROW}:{get_column_letter(len(QUALITY_COLUMNS))}{max(row, HEADER_ROW)}"
    )
    sheet.freeze_panes = f"A{HEADER_ROW + 1}"


def _quality_verdict(record: QualityRecord) -> str:
    if record.complete:
        return f"This history accounts for every dataset in view. {TOMBSTONE}"
    n = len(record.completeness.reasons)
    return (
        f"This history does not claim to be complete — "
        f"{words.count(n, 'reason')} on the Scope sheet."
    )


def _unchecked(sheet: Any, record: QualityRecord) -> None:
    sheet.column_dimensions["A"].width = 60

    sheet["A1"] = "Datasets with no assertions"
    sheet["A1"].font = TITLE
    sheet["A2"] = (
        "These appeared in lineage in the window and nothing asserted anything "
        "about them. Not checked is not the same as passed."
    )
    sheet["A2"].alignment = WRAP
    sheet.row_dimensions[2].height = 32

    # Every one of them, not a sample: this is the sheet somebody works
    # through, and a truncated work list is a finished work list.
    for offset, key in enumerate(record.unchecked):
        sheet.cell(row=4 + offset, column=1, value=key).alignment = TOP


def _quality_scope(sheet: Any, record: QualityRecord) -> None:
    scope = record.scope
    sheet.column_dimensions["A"].width = 26
    sheet.column_dimensions["B"].width = 96

    sheet["A1"] = "Scope of this history"
    sheet["A1"].font = TITLE

    rows = [("Source", scope.source or "unknown"), ("Window", scope.window())]
    rows += list(scope.lines())
    if scope.domains_source():
        rows.append(("Domains", scope.domains_source()))
    if scope.domains_silent:
        rows.append(("Declared but silent", ", ".join(scope.domains_silent)))

    row = 3
    for label, value in rows:
        sheet.cell(row=row, column=1, value=label[0].upper() + label[1:]).font = STRONG
        sheet.cell(row=row, column=2, value=value).alignment = WRAP
        row += 1

    row += 1
    sheet.cell(row=row, column=1, value="Not covered").font = STRONG
    sheet.cell(row=row, column=2, value=scope.OUT_OF_VIEW).alignment = WRAP
    sheet.row_dimensions[row].height = 64

    row += 2
    sheet.cell(row=row, column=1, value="Completeness").font = STRONG
    if record.complete:
        sheet.cell(row=row, column=2, value=_quality_verdict(record))
        return

    sheet.cell(row=row, column=2, value="This history does not claim to be complete.").font = STRONG
    for reason in record.completeness.reasons:
        row += 1
        sheet.cell(row=row, column=2, value=reason).alignment = WRAP


# --- the provenance chain ---------------------------------------------------

PROVENANCE_COLUMNS: tuple[tuple[str, int], ...] = (
    ("Depth", 8),
    ("Dataset", 44),
    ("Produced by", 34),
    ("Run", 38),
    ("When", 26),
    ("Repository", 40),
    ("Commit", 16),
    ("Branch", 14),
    ("Path", 34),
    ("Signature", 34),
    ("Chain ends", 44),
)

PROVENANCE_AT = {h: i for i, (h, _) in enumerate(PROVENANCE_COLUMNS, start=1)}


def provenance_workbook(record: ProvenanceRecord) -> bytes:
    """The chain as ``.xlsx`` bytes.

    One sheet, because a chain is one thing. Depth is a column rather than
    indentation: a reader who sorts the sheet would destroy indentation without
    noticing, and the depth is the part they would be sorting by.
    """
    book = Workbook()
    book.properties.creator = "qedro"
    book.properties.title = f"Provenance of {record.dataset}"
    book.properties.description = record.scope.OUT_OF_VIEW

    _chain(book.active, record)
    _provenance_scope(book.create_sheet("Scope"), record)

    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _chain(sheet: Any, record: ProvenanceRecord) -> None:
    sheet.title = "Chain"

    sheet["A1"] = f"Provenance of {record.dataset}"
    sheet["A1"].font = TITLE
    sheet["A2"] = record.controller.name or "No controller is declared"
    sheet["A2"].font = STRONG
    sheet["A3"] = (
        f"{record.scope.with_commit} of {record.scope.steps} steps name a commit, "
        f"{record.scope.with_signature} report a signature"
    )
    sheet["A4"] = _provenance_verdict(record)
    sheet["A4"].font = STRONG

    for index, (heading, width) in enumerate(PROVENANCE_COLUMNS, start=1):
        cell = sheet.cell(row=HEADER_ROW, column=index, value=heading)
        cell.font = HEADING
        cell.fill = HEADING_FILL
        cell.alignment = WRAP
        sheet.column_dimensions[get_column_letter(index)].width = width

    for offset, step in enumerate(record.steps):
        row = HEADER_ROW + 1 + offset
        p = step.production
        values = (
            step.depth,
            step.dataset,
            p.job if p else "",
            p.run_id if p else "",
            _when(p.when) if p else "",
            p.code.repository if p else "",
            p.code.short if p else "",
            p.code.branch if p else "",
            p.code.path if p else "",
            p.signature.describe() if p else "",
            step.ended,
        )
        for index, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=index, value=value)
            cell.alignment = WRAP if index == PROVENANCE_AT["Path"] else TOP

        # Tinted where the chain cannot show authorisation — and the cell says
        # which of the three reasons it is, so the colour carries nothing alone.
        if not p or not p.authorised:
            sheet.cell(row=row, column=PROVENANCE_AT["Signature"]).fill = ASSERTED_FILL
        if step.ended:
            sheet.cell(row=row, column=PROVENANCE_AT["Chain ends"]).fill = ASSERTED_FILL

    last = HEADER_ROW + len(record.steps)
    sheet.auto_filter.ref = (
        f"A{HEADER_ROW}:{get_column_letter(len(PROVENANCE_COLUMNS))}{max(last, HEADER_ROW)}"
    )
    sheet.freeze_panes = f"A{HEADER_ROW + 1}"


def _provenance_verdict(record: ProvenanceRecord) -> str:
    if record.complete:
        return f"Every step in this chain ran under a signed commit. {TOMBSTONE}"
    n = len(record.completeness.reasons)
    return (
        f"This chain does not claim to be a proof — {words.count(n, 'reason')} on the Scope sheet."
    )


def _provenance_scope(sheet: Any, record: ProvenanceRecord) -> None:
    scope = record.scope
    sheet.column_dimensions["A"].width = 26
    sheet.column_dimensions["B"].width = 96

    sheet["A1"] = "Scope of this chain"
    sheet["A1"].font = TITLE

    rows = [("Source", scope.source or "unknown"), ("Window", scope.window())]
    rows += list(scope.lines())

    row = 3
    for label, value in rows:
        sheet.cell(row=row, column=1, value=label[0].upper() + label[1:]).font = STRONG
        sheet.cell(row=row, column=2, value=value).alignment = WRAP
        row += 1

    row += 1
    sheet.cell(row=row, column=1, value="Not covered").font = STRONG
    sheet.cell(row=row, column=2, value=scope.OUT_OF_VIEW).alignment = WRAP
    sheet.row_dimensions[row].height = 64

    row += 2
    sheet.cell(row=row, column=1, value="Completeness").font = STRONG
    if record.complete:
        sheet.cell(row=row, column=2, value=_provenance_verdict(record))
        return

    sheet.cell(row=row, column=2, value="This chain does not claim to be a proof.").font = STRONG
    for reason in record.completeness.reasons:
        row += 1
        sheet.cell(row=row, column=2, value=reason).alignment = WRAP


# --- the deployer view ------------------------------------------------------

#: One row per use case, lineage and declared alike, so a reader filtering on
#: `Evidence` sees both kinds side by side instead of on separate sheets.
DEPLOYER_COLUMNS: tuple[tuple[str, int], ...] = (
    ("Use case", 38),
    ("Evidence", 22),
    ("Domain", 12),
    ("Purpose", 24),
    ("Purpose source", 20),
    ("Legal basis", 22),
    ("Legal basis source", 20),
    ("Model version", 34),
    ("Latest run", 38),
    ("Inputs read, latest run (context for Art. 26(4))", 40),
    ("Run records in view (context for Art. 26(6))", 44),
    ("Notes", 46),
)

DEPLOYER_AT = {h: i for i, (h, _) in enumerate(DEPLOYER_COLUMNS, start=1)}
DEPLOYER_WRAPPED = {
    DEPLOYER_AT["Model version"],
    DEPLOYER_AT["Inputs read, latest run (context for Art. 26(4))"],
    DEPLOYER_AT["Run records in view (context for Art. 26(6))"],
    DEPLOYER_AT["Notes"],
}


def deployer_workbook(record: DeployerRecord) -> bytes:
    """The deployer view as ``.xlsx`` bytes.

    Row 3 carries the legal reference and its condition, above the table, for
    the same reason the verdict does: a sheet read without it would imply that
    Art. 26 applies today.
    """
    book = Workbook()
    book.properties.creator = "qedro"
    book.properties.title = "AI use cases, deployer view of the Art. 30 record"
    book.properties.description = record.scope.OUT_OF_VIEW

    _use_cases(book.active, record)
    _deployer_scope(book.create_sheet("Scope"), record)

    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _use_cases(sheet: Any, record: DeployerRecord) -> None:
    sheet.title = "AI use cases"

    sheet["A1"] = "AI use cases, deployer view of the Art. 30 record"
    sheet["A1"].font = TITLE
    sheet["A2"] = record.controller.name or "No controller is declared"
    sheet["A2"].font = STRONG
    sheet["A3"] = f"{record.regulation}. {record.application}"
    sheet["A4"] = _deployer_verdict(record)
    sheet["A4"].font = STRONG

    for index, (heading, width) in enumerate(DEPLOYER_COLUMNS, start=1):
        cell = sheet.cell(row=HEADER_ROW, column=index, value=heading)
        cell.font = HEADING
        cell.fill = HEADING_FILL
        cell.alignment = WRAP
        sheet.column_dimensions[get_column_letter(index)].width = width

    row = HEADER_ROW
    for use_case in record.use_cases:
        row += 1
        a = use_case.activity
        first, last, days = a.first_seen, a.last_seen, use_case.span_days
        if days is None or first is None or last is None:
            records = "no dated run records in view"
        else:
            enough = "at least six months" if days >= SIX_MONTHS else "less than six months"
            records = (
                f"{words.count(a.runs, 'run')}, {first.date()} to {last.date()}, "
                f"{words.count(days, 'day')} — {enough} of records in view"
            )
        versions = [
            f"{m.version} ({words.count(m.runs, 'run')}, reported by {m.reported_by})"
            for m in use_case.models
        ]
        if use_case.runs_without_model:
            versions.append(f"none reported ({words.count(use_case.runs_without_model, 'run')})")
        latest = use_case.latest
        values = (
            a.key,
            "emitted lineage",
            a.domain,
            a.purpose.value or "—",
            _source(a.purpose),
            a.legal_basis.value or "—",
            _source(a.legal_basis),
            "\n".join(versions),
            f"{latest.run_id}\n{_when(latest.when)}",
            "\n".join(latest.inputs),
            records,
            "\n".join(a.gaps()),
        )
        _deployer_row(sheet, row, values)
        for value_column, source_column, sourced in (
            (DEPLOYER_AT["Purpose"], DEPLOYER_AT["Purpose source"], a.purpose),
            (DEPLOYER_AT["Legal basis"], DEPLOYER_AT["Legal basis source"], a.legal_basis),
        ):
            if not sourced.evidenced:
                sheet.cell(row=row, column=source_column).fill = ASSERTED_FILL
            if sourced.unrecognised:
                sheet.cell(row=row, column=value_column).fill = ASSERTED_FILL

    for entry in record.declared:
        row += 1
        values = (
            entry.name,
            "declared, no lineage",
            entry.domain,
            entry.purpose.value or "—",
            _source(entry.purpose),
            entry.legal_basis.value or "—",
            _source(entry.legal_basis),
            f"{entry.model} (declared)" if entry.model else "not declared",
            "none",
            "\n".join(f"{i} (declared)" for i in entry.inputs) or "not declared",
            "none — nothing emits lineage for this use",
            entry.note,
        )
        _deployer_row(sheet, row, values)
        # The whole row is an assertion, so the cell that says so is tinted —
        # and says so in words, which is what carries it.
        sheet.cell(row=row, column=DEPLOYER_AT["Evidence"]).fill = ASSERTED_FILL

    last_column = get_column_letter(len(DEPLOYER_COLUMNS))
    sheet.auto_filter.ref = f"A{HEADER_ROW}:{last_column}{max(row, HEADER_ROW)}"
    sheet.freeze_panes = f"A{HEADER_ROW + 1}"


def _deployer_row(sheet: Any, row: int, values: tuple) -> None:
    for index, value in enumerate(values, start=1):
        cell = sheet.cell(row=row, column=index, value=value)
        cell.alignment = WRAP if index in DEPLOYER_WRAPPED else TOP


def _deployer_verdict(record: DeployerRecord) -> str:
    if record.complete:
        return f"Every AI use case in this view stands on emitted evidence. {TOMBSTONE}"
    n = len(record.completeness.reasons)
    return (
        f"This view does not claim to be a proof — {words.count(n, 'reason')} on the Scope sheet."
    )


def _deployer_scope(sheet: Any, record: DeployerRecord) -> None:
    scope = record.scope
    sheet.column_dimensions["A"].width = 26
    sheet.column_dimensions["B"].width = 96

    sheet["A1"] = "Scope of this view"
    sheet["A1"].font = TITLE

    rows = [
        ("Law", f"{record.regulation}. {record.application}"),
        ("Source", scope.source or "unknown"),
        ("Window", scope.window()),
    ]
    rows += list(scope.lines())

    row = 3
    for label, value in rows:
        sheet.cell(row=row, column=1, value=label[0].upper() + label[1:]).font = STRONG
        sheet.cell(row=row, column=2, value=value).alignment = WRAP
        row += 1

    row += 1
    sheet.cell(row=row, column=1, value="Not covered").font = STRONG
    sheet.cell(row=row, column=2, value=scope.OUT_OF_VIEW).alignment = WRAP
    sheet.row_dimensions[row].height = 96

    row += 2
    sheet.cell(row=row, column=1, value="Completeness").font = STRONG
    if record.complete:
        sheet.cell(row=row, column=2, value=_deployer_verdict(record))
        return

    sheet.cell(row=row, column=2, value="This view does not claim to be a proof.").font = STRONG
    for reason in record.completeness.reasons:
        row += 1
        sheet.cell(row=row, column=2, value=reason).alignment = WRAP
