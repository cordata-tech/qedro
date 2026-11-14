"""Any rendered output as searchable text, whatever the format.

A binary format is where a property like *the scope statement is always
printed* would quietly stop being checked, so the workbook and the PDF are read
back and flattened rather than skipped. Whitespace is normalised, because the
terminal format wraps its paragraphs and a PDF breaks its lines wherever the
page does, and a phrase that straddles a break is still present in the output.
"""

from __future__ import annotations

from io import BytesIO


def as_text(rendered: str | bytes) -> str:
    if isinstance(rendered, bytes) and rendered.startswith(b"%PDF"):
        from pypdf import PdfReader

        rendered = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(rendered)).pages
        )
    elif isinstance(rendered, bytes):
        from openpyxl import load_workbook

        book = load_workbook(BytesIO(rendered))
        rendered = "\n".join(
            str(cell.value)
            for sheet in book.worksheets
            for row in sheet.iter_rows()
            for cell in row
            if cell.value is not None
        )
    return " ".join(rendered.split())
