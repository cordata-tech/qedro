"""Rendering, and the two properties every format has to keep — for every projection.

**The scope statement is unconditional.** A format that prints it only when
something went wrong has taught the reader that its absence means full coverage.

**Provenance survives.** A format that flattens *emitted by the pipeline* into
*typed into a file* has thrown away the only thing that makes this record
different from one a person maintained by hand.

Both are asserted per format **and per projection**, because the renderers
dispatch on the artefact: a `quality` implementation that forgot the scope
statement would be invisible to a test that only ever passed it a `ropa`
record. A renderer added later, or a projection added later, is exactly where
these get dropped.
"""

from __future__ import annotations

import json as json_lib
from io import BytesIO

import pytest
from openpyxl import load_workbook

from qedro import TOMBSTONE, config, deployer, provenance, quality, render, vocabulary
from qedro.ropa import build

from .test_deployer import a_declared
from .test_deployer import event as deployer_event
from .test_provenance import event as provenance_event
from .test_quality import check
from .test_quality import event as quality_event
from .test_ropa import EVIDENCED, event

WORDS = vocabulary.load()
FORMATS = sorted(render.FORMATS)


def record(events, cfg="controller: ACME GmbH\n"):
    return build(events, config=config.parse(cfg), vocabulary=WORDS, report=None)


def ropa_record(cfg="controller: ACME GmbH\n"):
    return record([event(facet=EVIDENCED)], cfg)


def quality_record(cfg="controller: ACME GmbH\n"):
    return quality.build(
        [quality_event(assertions=[check()]), quality_event(reads="wh/unchecked")],
        config=config.parse(cfg),
    )


def provenance_record(cfg="controller: ACME GmbH\n"):
    return provenance.build(
        [provenance_event(writes=["scores"], reads=["raw"])],
        dataset="wh/scores",
        config=config.parse(cfg),
    )


def deployer_record(cfg="controller: ACME GmbH\n"):
    # No processing facet, so the view always withholds the mark and the
    # reasons property has something to check in every format.
    events = [deployer_event(model="2026-06-fraud-v3")]
    record = build(events, config=config.parse(cfg), vocabulary=WORDS, declared=a_declared())
    return deployer.build(record, events)


#: Every artefact a renderer can be handed. The properties below hold for all
#: of them or they are not properties.
PROJECTIONS = {
    "ropa": ropa_record,
    "quality": quality_record,
    "provenance": provenance_record,
    "deployer": deployer_record,
}
CASES = [(p, f) for p in sorted(PROJECTIONS) for f in FORMATS]

#: Projections that make a claim about domain coverage. `provenance` does not
#: — a chain is about one dataset — so it carries no declared domains and can
#: have no silent ones. Neither does the deployer view, which leaves domain
#: coverage to the Art. 30 view it is built from. Excluded from that property
#: rather than exempted from it quietly.
DOMAIN_AWARE = ["ropa", "quality"]
DOMAIN_CASES = [(p, f) for p in DOMAIN_AWARE for f in FORMATS]


def readable(record, fmt):
    """Any format as searchable text, so one property can be asserted of all of them.

    A binary format is where a property like *the scope statement is always
    printed* would quietly stop being checked — so xlsx is read back and
    flattened rather than skipped.
    """
    out = render.FORMATS[fmt](record)
    if isinstance(out, bytes):
        book = load_workbook(BytesIO(out))
        out = "\n".join(
            str(cell.value)
            for sheet in book.worksheets
            for row in sheet.iter_rows()
            for cell in row
            if cell.value is not None
        )
    # Whitespace-normalised, because the terminal format wraps its paragraphs
    # and a phrase that straddles a line break is still present in the output.
    return " ".join(out.split())


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
    def test_the_art30_items_not_covered_are_named_on_a_run_that_earns_the_mark(self, fmt):
        # The case a later simplification would drop first: a complete record
        # still has no field for (c)-(g), and must still say so. See #12.
        built = record([event(facet=EVIDENCED)])
        assert built.complete
        if fmt == "json":
            art30 = json_lib.loads(render.FORMATS[fmt](built))["scope"]["art30"]
            assert art30["covered"] == ["a", "b", "c", "d", "e", "f", "g"]
            assert art30["not_covered"] == []
        else:
            out = rendered([event(facet=EVIDENCED)], fmt)
            assert "(d) categories of recipients" in out
            assert "(d) and (g) can only be declared" in out

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_recipients_and_security_measures_are_marked_as_asserted(self, fmt):
        # Nothing emits either, so an unmarked value would read as evidence the
        # record does not have. See #13, slice 4.
        cfg = (
            "controller: ACME GmbH\n"
            'jobs:\n  "*":\n'
            "    recipients: the group's fraud bureau\n"
            "    security_measures: pseudonymisation at rest\n"
        )
        built = record([event(facet=EVIDENCED)], cfg)
        if fmt == "json":
            [activity] = json_lib.loads(render.FORMATS[fmt](built))["activities"]
            assert activity["recipients"] == {
                "values": ["the group's fraud bureau"],
                "provenance": "mapping",
            }
        else:
            out = readable(built, fmt)
            assert "the group's fraud bureau" in out
            assert "declared" in out

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_classification_and_what_was_not_classified_survive(self, fmt):
        # Both halves: the category an activity reports, and the datasets that
        # carried none, which must never read as *no personal data*. See #13.
        from .test_ropa import tagged

        built = record(
            [
                tagged(
                    reads=[("wh/vendor_feed", {})],
                    writes=[("wh/scores", {"special_category": "health"})],
                )
            ]
        )
        if fmt == "json":
            [activity] = json_lib.loads(render.FORMATS[fmt](built))["activities"]
            assert activity["classification"][0]["value"] == "health"
            assert activity["classification"][0]["art30_item"] == "c"
            assert activity["unclassified"] == ["wh/vendor_feed"]
        else:
            out = readable(built, fmt)
            assert "health" in out
            assert "wh/vendor_feed" in out

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_a_read_only_activity_is_named(self, fmt):
        # See #22. JSON carries the list; the others carry the sentence.
        from .test_ropa import reading

        built = record([reading("monitor")])
        if fmt == "json":
            scope = json_lib.loads(render.FORMATS[fmt](built))["scope"]
            assert scope["read_only"] == ["acme.fraud/monitor"]
        else:
            assert "1 activity read datasets and wrote none: acme.fraud/monitor" in readable(
                built, fmt
            )

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
        # The record table only. Since #13 a second table follows it, saying
        # what the data each activity touched is.
        record_table = out.split("## What the data is")[0]
        assert record_table.count("| `acme.fraud/") == 2

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


class TestEveryProjectionKeepsTheProperties:
    """The renderers dispatch on the artefact, so both axes are asserted.

    A `quality` renderer that dropped the scope statement would sail past a
    test that only ever handed it a `ropa` record — which is the failure mode
    `singledispatch` introduces and this class exists to close.
    """

    @pytest.mark.parametrize(("projection", "fmt"), CASES)
    def test_the_scope_statement_is_printed(self, projection, fmt):
        built = PROJECTIONS[projection]()
        out = readable(built, fmt)
        # Its own sentence, not a shared one: each projection's out-of-view
        # paragraph has to be true of that artefact.
        assert " ".join(built.scope.OUT_OF_VIEW.split()) in out

    @pytest.mark.parametrize(("projection", "fmt"), CASES)
    def test_the_window_is_stated(self, projection, fmt):
        assert "2026-03-01" in readable(PROJECTIONS[projection](), fmt)

    @pytest.mark.parametrize(("projection", "fmt"), DOMAIN_CASES)
    def test_a_silent_domain_is_named(self, projection, fmt):
        cfg = "controller: ACME GmbH\ndomains: [fraud, marketing]\n"
        assert "marketing" in readable(PROJECTIONS[projection](cfg), fmt)

    @pytest.mark.parametrize(("projection", "fmt"), DOMAIN_CASES)
    def test_a_guessed_domain_is_said_to_be_guessed(self, projection, fmt):
        # Otherwise a wrong guess and a silent domain read the same. See #9.
        # JSON carries the lists rather than the sentence, like every scope count.
        cfg = "controller: ACME GmbH\ndomains: [fraud, marketing]\n"
        built = PROJECTIONS[projection](cfg)
        if fmt == "json":
            scope = json_lib.loads(render.FORMATS[fmt](built))["scope"]
            assert (scope["domains_guessed"], scope["domains_mapped"]) == (["fraud"], [])
        else:
            assert "fraud guessed from the job namespace" in readable(built, fmt)

    @pytest.mark.parametrize("projection", sorted(PROJECTIONS))
    def test_a_wrapped_line_never_ends_with_art(self, projection):
        # `Art.` at the end of one line and `5(1)(e)` at the start of the next
        # reads as two different things, and a reader checking a legal
        # reference is the one who cannot afford that.
        out = render.text(PROJECTIONS[projection]("controller: ACME GmbH\ndomains: [fraud]\n"))
        assert not [line for line in out.splitlines() if line.rstrip().endswith("Art.")]

    @pytest.mark.parametrize(("projection", "fmt"), CASES)
    def test_a_withheld_mark_carries_its_reasons(self, projection, fmt):
        # Every projection withholds here, for its own reasons: ropa and
        # quality for the silent domain, provenance for the unknown signature.
        cfg = "controller: ACME GmbH\ndomains: [fraud, marketing]\n"
        built = PROJECTIONS[projection](cfg)
        assert not built.complete
        out = readable(built, fmt)
        for reason in built.completeness.reasons:
            assert " ".join(reason.split()) in out, f"{projection}/{fmt} dropped a reason"


class TestQualityRendering:
    """What only this projection can get wrong."""

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_the_domain_filter_and_what_it_left_out_are_rendered(self, fmt):
        # A dataset left out by a wrong domain guess is otherwise
        # indistinguishable from one that does not exist. See #11.
        built = quality.build(
            [
                quality_event(assertions=[check()]),
                quality_event(namespace="acme.crm", job="curate", reads="wh/leads"),
            ],
            config=config.parse("controller: ACME GmbH\n"),
            domains=["fraud"],
        )
        if fmt == "json":
            scope = json_lib.loads(render.FORMATS[fmt](built))["scope"]
            assert scope["domains_filter"] == ["fraud"]
            assert scope["left_out"] == [{"domain": "crm", "datasets": 1, "guessed": True}]
        else:
            out = readable(built, fmt)
            assert (
                "--domain fraud left out 1 dataset: 1 in crm (guessed from the job namespace)"
                in out
            )

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_unchecked_datasets_are_named_not_only_counted(self, fmt):
        # The names are what somebody acts on. A count alone is a fact nobody
        # can do anything with.
        assert "wh/unchecked" in readable(quality_record(), fmt)

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_a_failure_is_distinguishable_from_a_pass(self, fmt):
        failing = quality.build(
            [quality_event(assertions=[check(success=False)])],
            config=config.parse("controller: A\n"),
        )
        holding = quality.build(
            [quality_event(assertions=[check()])], config=config.parse("controller: A\n")
        )
        assert readable(failing, fmt) != readable(holding, fmt)
        assert "fail" in readable(failing, fmt).lower()

    def test_the_text_form_says_not_checked_in_words(self):
        out = render.text(quality_record())
        assert "Not checked" in out

    def test_json_carries_the_unchecked_list_not_a_number(self):
        payload = json_lib.loads(render.json(quality_record()))
        assert payload["unchecked"] == ["wh/unchecked"]
        assert payload["scope"]["checked"] == 1

    def test_a_renderer_refuses_an_artefact_it_does_not_know(self):
        # singledispatch falls back to the base implementation, which must not
        # quietly render something wrong.
        with pytest.raises(TypeError):
            render.text(object())


class TestProvenanceRendering:
    """What only the chain can get wrong."""

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_an_unknown_signature_is_never_rendered_as_unsigned(self, fmt):
        out = readable(provenance_record(), fmt).lower()
        assert "unknown" in out
        assert "not signed" not in out

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_a_reported_signature_names_what_reported_it(self, fmt):
        built = provenance.build(
            [provenance_event(writes=["scores"], signed=True)],
            dataset="wh/scores",
            config=config.parse("controller: A\n"),
        )
        assert "cordata_provenance" in readable(built, fmt)

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_a_chain_that_ended_says_why_in_the_row(self, fmt):
        assert "nothing in the window produced it" in readable(provenance_record(), fmt)

    def test_json_keeps_the_signature_tri_state(self):
        payload = json_lib.loads(render.json(provenance_record()))
        [step] = [s for s in payload["steps"] if s["production"]]
        # null, never false: a consumer reading false would be inventing a
        # finding the chain does not support.
        assert step["production"]["signed"] is None
        assert step["production"]["authorised"] is False

    def test_the_text_form_indents_by_depth(self):
        out = render.text(provenance_record())
        assert "\n  wh/scores" in out
        assert "\n    wh/raw" in out


class TestDeployerRendering:
    """What only the deployer view can get wrong, asserted in every format."""

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_the_consolidated_text_is_cited(self, fmt):
        assert "02024R1689-20260727" in readable(deployer_record(), fmt)

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_art_26_is_never_shown_without_its_date(self, fmt):
        # The deployer duties apply to Annex III high-risk systems from
        # 2 December 2027. A format that cited Art. 26 without that would
        # imply they apply today.
        out = readable(deployer_record(), fmt)
        assert "Art. 26" in out or "article_26" in out
        assert "2 December 2027" in out or "2027-12-02" in out

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_a_declared_use_case_is_marked_as_declared(self, fmt):
        out = readable(deployer_record(), fmt)
        assert "support-reply-drafts" in out
        assert "declared" in out

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_the_model_version_is_named(self, fmt):
        assert "2026-06-fraud-v3" in readable(deployer_record(), fmt)

    def test_json_says_what_is_evidence_and_what_is_declared(self):
        payload = json_lib.loads(render.json(deployer_record()))
        assert payload["use_cases"][0]["evidence"] == "lineage"
        assert payload["declared"][0]["evidence"] == "declared"
        assert payload["declared"][0]["purpose"]["provenance"] == "declared"
        assert payload["declared"][0]["run_records"] is None

    def test_json_never_carries_a_retention_policy(self):
        payload = json_lib.loads(render.json(deployer_record()))
        assert payload["use_cases"][0]["run_records"]["retention_policy"] is None

    def test_json_does_not_decide_the_risk_tier(self):
        payload = json_lib.loads(render.json(deployer_record()))
        assert payload["references"]["high_risk_decided"] is False


def declared_art30_record():
    """An Art. 30 record with one evidenced activity and one declared one."""
    return build(
        [event(facet=EVIDENCED)],
        config=config.parse("controller: ACME GmbH\n"),
        vocabulary=WORDS,
        declared=a_declared(model=""),
    )


class TestDeclaredActivitiesInTheArt30View:
    """cordata-tech/qedro#6, asserted in every format."""

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_a_declared_activity_is_named_and_marked(self, fmt):
        out = readable(declared_art30_record(), fmt)
        assert "support-reply-drafts" in out
        assert "declared" in out

    @pytest.mark.parametrize("fmt", [f for f in FORMATS if f != "json"])
    def test_what_the_events_would_have_said_is_no_lineage_not_blank(self, fmt):
        # An empty Reads cell reads as *touches no data* and 0 runs as *ran
        # zero times*. Neither is known.
        assert "no lineage" in readable(declared_art30_record(), fmt)

    def test_json_uses_null_rather_than_an_empty_list(self):
        payload = json_lib.loads(render.json(declared_art30_record()))
        [entry] = payload["declared"]
        assert entry["reads"] is None and entry["runs"] is None
        assert entry["purpose"]["provenance"] == "declared"
        assert payload["scope"]["declared"] == 1

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_the_scope_statement_is_still_printed_and_still_true(self, fmt):
        built = declared_art30_record()
        out = readable(built, fmt)
        assert " ".join(built.scope.OUT_OF_VIEW.split()) in out
        assert "unless they are declared" in out

    def test_the_mark_is_withheld_with_its_reason_in_text(self):
        out = render.text(declared_art30_record())
        assert TOMBSTONE not in out
        assert "declared with no lineage" in out


class TestArt26ReferencesAreContextNotEvidence:
    """From the platform-side review of #7: an article number beside a list of
    inputs read as if the view had checked representativeness. It had not."""

    @pytest.mark.parametrize("fmt", [f for f in FORMATS if f != "json"])
    def test_the_inputs_are_context_for_art_26_4(self, fmt):
        assert "context for Art. 26(4)" in readable(deployer_record(), fmt)

    @pytest.mark.parametrize("fmt", [f for f in FORMATS if f != "json"])
    def test_the_records_are_context_for_art_26_6(self, fmt):
        assert "context for Art. 26(6)" in readable(deployer_record(), fmt)

    def test_the_text_form_says_what_they_are_not(self):
        # Whitespace-normalised: the sentence wraps under the value it explains.
        out = " ".join(render.text(deployer_record()).split())
        assert "not a check of relevance or representativeness" in out
        assert "not a retention policy or a compliance finding" in out


class TestOrchestrationParentsAreNamedInEveryFormat:
    """cordata-tech/qedro#8: a job left out of the activities is named in the scope."""

    @pytest.mark.parametrize("fmt", FORMATS)
    def test_the_parent_is_named(self, fmt):
        from .test_ropa import orchestrated

        built = build(orchestrated(), config=config.parse("controller: A\n"), vocabulary=WORDS)
        out = readable(built, fmt)
        assert "dbt/dbt-run-project" in out

    def test_json_lists_the_parents(self):
        from .test_ropa import orchestrated

        built = build(orchestrated(), config=config.parse("controller: A\n"), vocabulary=WORDS)
        payload = json_lib.loads(render.json(built))
        assert payload["scope"]["parents"] == ["dbt/dbt-run-project"]
        assert [a["job"] for a in payload["activities"]] == ["dbt/model.orders"]
