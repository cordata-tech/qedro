"""Rendering, and the two properties every format has to keep.

**The scope statement is unconditional.** A format that prints it only when
something went wrong has taught the reader that its absence means full coverage.

**Provenance survives.** A format that flattens *emitted by the pipeline* into
*typed into a file* has thrown away the only thing that makes this record
different from one a person maintained by hand.

Both are asserted per format rather than once, because a renderer added later
is exactly where they get dropped.
"""

from __future__ import annotations

import json as json_lib
from io import BytesIO

import pytest
from openpyxl import load_workbook

from qedro import TOMBSTONE, config, render, vocabulary
from qedro.ropa import build

from .test_ropa import EVIDENCED, event

WORDS = vocabulary.load()
FORMATS = sorted(render.FORMATS)


def record(events, cfg="controller: ACME GmbH\n"):
    return build(events, config=config.parse(cfg), vocabulary=WORDS, report=None)


def readable(record, fmt):
    """Any format as searchable text, so one property can be asserted of all of them.

    A binary format is where a property like *the scope statement is always
    printed* would quietly stop being checked — so xlsx is read back and
    flattened rather than skipped.
    """
    out = render.FORMATS[fmt](record)
    if not isinstance(out, bytes):
        return out
    book = load_workbook(BytesIO(out))
    return "\n".join(
        str(cell.value)
        for sheet in book.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )


def rendered(events, fmt, cfg="controller: ACME GmbH\n"):
    return readable(record(events, cfg), fmt)


class TestEveryFormatStatesItsScope:
    """cordata-tech/qedro#3."""

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_on_a_run_that_earns_the_tombstone(self, fmt):
        out = rendered([event(facet=EVIDENCED)], fmt)
        assert "not represented here" in out, f"{fmt} dropped the scope statement"

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_on_a_run_that_does_not(self, fmt):
        assert "not represented here" in rendered([event()], fmt)

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_the_window_is_stated(self, fmt):
        assert "2026-03-01" in rendered([event(facet=EVIDENCED)], fmt)

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_a_silent_domain_is_named(self, fmt):
        out = rendered(
            [event(facet=EVIDENCED)], fmt, "controller: ACME GmbH\ndomains: [fraud, marketing]\n"
        )
        assert "marketing" in out


class TestProvenanceSurvives:
    @pytest.mark.parametrize("fmt", FORMATS)
    def test_an_asserted_value_is_distinguishable_from_an_evidenced_one(self, fmt):
        mapped = rendered(
            [event()],
            fmt,
            'controller: ACME GmbH\njobs:\n  "*": {purpose: p, legal_basis: consent}\n',
        )
        evidenced = rendered([event(facet=EVIDENCED)], fmt)
        assert "mapping" in mapped.lower(), f"{fmt} hides that the value came from a file"
        assert mapped != evidenced

    def test_json_carries_provenance_per_field_not_per_row(self):
        # A consumer should not have to re-derive which of the two fields was
        # evidenced when only one of them was.
        payload = json_lib.loads(
            rendered(
                [event(facet={"purpose": "fraud-detection"})],
                "json",
                'controller: ACME GmbH\njobs:\n  "*": {legal_basis: consent}\n',
            )
        )
        [activity] = payload["activities"]
        assert activity["purpose"]["provenance"] == "facet"
        assert activity["legal_basis"]["provenance"] == "mapping"


class TestTheMark:
    def test_printed_when_earned(self):
        assert TOMBSTONE in render.text(record([event(facet=EVIDENCED)]))

    def test_withheld_otherwise(self):
        assert TOMBSTONE not in render.text(record([event()]))

    def test_the_reasons_are_printed_not_only_counted(self):
        out = render.text(record([event()]))
        assert "no purpose or no legal basis" in out

    def test_no_symbol_for_terminals_without_the_glyph(self):
        out = render.text(record([event(facet=EVIDENCED)]), symbol=False)
        assert TOMBSTONE not in out and "[complete]" in out

    def test_markdown_says_so_in_words_as_well(self):
        # A mark in a document somebody prints needs a text equivalent; a bare
        # glyph conveying *complete* is not sufficient on its own.
        out = render.markdown(record([event(facet=EVIDENCED)]))
        assert "stands on emitted evidence" in out


class TestTheRecordIsReadable:
    def test_the_controller_is_named(self):
        # Art. 30(1)(a). A record with no controller on it is not an Art. 30
        # record, so its absence has to be visible rather than blank.
        assert "ACME GmbH" in render.text(record([event(facet=EVIDENCED)]))

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_a_missing_controller_is_a_stated_hole_not_a_blank(self, fmt):
        # Art. 30(1)(a). A record that does not name its controller is not an
        # Art. 30 record, so a blank field is not enough — it has to be a
        # reason the artefact gives for not claiming to be a proof.
        out = readable(build([event()], config=config.Config(), vocabulary=WORDS), fmt)
        assert "no controller is declared" in out

    def test_json_is_valid_json(self):
        json_lib.loads(rendered([event(facet=EVIDENCED)], "json"))

    def test_markdown_table_has_a_row_per_activity(self):
        out = render.markdown(record([event(name="a"), event(name="b")]))
        assert out.count("| `acme.fraud/") == 2

    def test_an_unrecognised_value_is_flagged_in_text(self):
        out = render.text(record([event(facet={"purpose": "p", "legal_basis": "vibes"})]))
        assert "not in vocabulary" in out


class TestFormatInference:
    """`--out ropa.md` means markdown.

    Filling a `.md` file with terminal text would be a small lie, and this is
    the one artefact that should not contain any.
    """

    def test_a_markdown_suffix(self):
        assert render.infer("ropa.md") == "markdown"
        assert render.infer("ropa.markdown") == "markdown"

    def test_a_json_suffix(self):
        assert render.infer("record.json") == "json"

    def test_an_xlsx_suffix(self):
        assert render.infer("ropa.xlsx") == "xlsx"

    def test_an_unknown_suffix_falls_back(self):
        assert render.infer("ropa.pdf") == "text"

    def test_no_output_file_at_all(self):
        assert render.infer(None) == "text"

    def test_a_path_with_dots_in_the_directory(self):
        # `./out.d/ropa` has a dot but no suffix on the filename.
        assert render.infer("out.d/ropa") == "text"
