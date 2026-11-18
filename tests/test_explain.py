"""Every value explained in a sentence, and never more than its source says (#48)."""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from qedro import config, declared, document, explain, references, render, ropa, signoff
from qedro import vocabulary as vocabulary_module
from qedro.errors import ConfigError
from qedro.sources import read

#: Words that would turn an explanation into a judgement. Whether a value is the
#: right one is a person's call (#41); an explanation only says where it is from.
JUDGEMENT = re.compile(
    r"\b(lawful|unlawful|valid|invalid|correct|incorrect|compliant|compliance|"
    r"verified|proves?|proven|approved|sufficient|adequate)\b",
    re.IGNORECASE,
)


def demo_record(lineage: str = "demo/lineage") -> ropa.Record:
    events, report = read(lineage)
    vocab = vocabulary_module.load()
    return ropa.build(
        events,
        config=config.load("demo/qedro.yaml"),
        vocabulary=vocab,
        report=report,
        declared=declared.load("demo/activities.yaml", vocabulary=vocab),
    )


def all_explanations(record: ropa.Record) -> list[tuple[str, dict, explain.Explanation]]:
    """Every explanation in a record, with the facts it was allowed to use."""
    refs, vocab = record.references, record.vocabulary
    out = []
    for a in record.activities:
        for name in ("purpose", "legal_basis"):
            s = getattr(a, name)
            facts = {a.key, s.run, s.rule, s.value, vocab, "processing"}
            if a.rule:
                facts.add(a.rule.pattern)
            out.append(
                (
                    s.provenance,
                    facts,
                    explain.activity_value(a, name, s, references=refs, vocabulary=vocab),
                )
            )
        for name in ("recipients", "security_measures"):
            facts = {a.key, a.rule.pattern if a.rule else ""}
            out.append(
                ("list", facts, explain.activity_list(a, name, getattr(a, name), references=refs))
            )
    for d in record.declared:
        for name in ("purpose", "legal_basis"):
            s = getattr(d, name)
            out.append(
                (
                    s.provenance,
                    {d.name, s.value, vocab},
                    explain.declared_value(d, name, s, references=refs, vocabulary=vocab),
                )
            )
    tag_keys = set(explain.CLASSIFICATION_LABELS)
    for a in record.activities:
        for c in a.classification:
            facts = {a.key, f"{c.key}: {c.value}", c.value, vocab, "tags"}
            facts |= {*c.reads, *c.writes, *c.declared_by}
            out.append(
                (
                    "classification",
                    facts,
                    explain.classification(a, c, references=refs, vocabulary=vocab),
                )
            )
    for dataset in record.scope.unclassified:
        touched = [a.key for a in record.activities if dataset in a.unclassified]
        out.append(
            (
                "unclassified",
                {dataset, "tags", *tag_keys, *touched},
                explain.unclassified(dataset, touched, references=refs),
            )
        )
    out.append(
        ("controller", {"controller"}, explain.controller(record.controller, references=refs))
    )
    return out


@pytest.fixture(scope="module")
def asserted() -> ropa.Record:
    return demo_record("demo/lineage")


@pytest.fixture(scope="module")
def evidenced() -> ropa.Record:
    return demo_record("demo/lineage-declared")


class TestNeverMoreThanTheSource:
    @pytest.mark.parametrize("which", ["asserted", "evidenced"])
    def test_every_name_in_backticks_is_a_fact_the_record_holds(self, which, request):
        record = request.getfixturevalue(which)
        for _, facts, e in all_explanations(record):
            for named in re.findall(r"`([^`]+)`", e.text):
                assert named in facts, f"{named!r} is not something the record holds: {e.text}"

    @pytest.mark.parametrize("which", ["asserted", "evidenced"])
    def test_no_explanation_judges(self, which, request):
        record = request.getfixturevalue(which)
        for _, _, e in all_explanations(record):
            # A value in backticks is the record's own word, not the sentence's.
            prose = re.sub(r"`[^`]+`", "", e.text)
            assert not JUDGEMENT.search(prose), e.text

    def test_only_an_emitted_value_is_said_to_be_emitted_by_the_job(self, asserted, evidenced):
        for record in (asserted, evidenced):
            for provenance, _, e in all_explanations(record):
                says_emitted = e.text.startswith("Emitted by")
                assert says_emitted == (provenance is ropa.Provenance.FACET), e.text

    def test_an_emitted_value_rests_on_the_run_that_carried_it(self, evidenced):
        a = next(a for a in evidenced.activities if a.purpose.provenance.evidenced)
        e = explain.activity_value(
            a, "purpose", a.purpose, references=evidenced.references, vocabulary="v"
        )
        assert e.rests_on == (explain.Link("run", a.purpose.run),)
        assert a.purpose.run in e.text

    def test_an_asserted_value_names_its_rule_and_the_line_it_is_on(self, asserted):
        a = next(a for a in asserted.activities if a.purpose.provenance is ropa.Provenance.MAPPING)
        e = explain.activity_value(
            a, "purpose", a.purpose, references=asserted.references, vocabulary="v"
        )
        (link,) = e.rests_on
        assert (link.kind, link.id, link.file) == ("rule", a.purpose.rule, "demo/qedro.yaml")
        line = Path("demo/qedro.yaml").read_text(encoding="utf-8").splitlines()[link.line - 1]
        assert line.strip().strip('":') == a.purpose.rule

    def test_an_absent_value_says_which_sources_were_silent_and_names_no_value(self, asserted):
        a = next(a for a in asserted.activities if not a.purpose)
        e = explain.activity_value(
            a, "purpose", a.purpose, references=asserted.references, vocabulary="v"
        )
        assert e.text.startswith("Nothing states a purpose:")
        assert "no rule in demo/qedro.yaml matches it" in e.text


class TestTheRequirementEachFieldAnswers:
    def test_purpose_and_legal_basis_cite_their_articles(self, asserted):
        refs = asserted.references
        assert refs.answers("purpose").cite == "Art. 30(1)(b) GDPR"
        assert refs.answers("legal_basis").cite == "Art. 6(1) GDPR"
        assert refs.answers("record").cite == "Art. 5(2) GDPR"

    def test_the_wording_is_quoted_once_in_the_json(self, asserted):
        payload = json.loads(render.json(asserted))
        assert payload["references"]["requirements"]["art-30-1-b"]["text"] == (
            "the purposes of the processing;"
        )
        purpose = payload["explain"]["activities"]["acme.crm/consent-sync"]["purpose"]
        assert purpose["answers"] == "art-30-1-b"
        assert "text" not in payload["references"]["requirements"]["art-30-1-b"]["cite"]

    def test_a_field_the_document_maps_to_nothing_answers_nothing(self):
        refs = references.parse(
            "references:\n  x:\n    cite: X\n    text: wording\nfields:\n  purpose: x\n",
            origin="r.yaml",
        )
        assert refs.answers("legal_basis") is None


class TestTheReferencesAreData:
    def test_the_shipped_document_loads_at_runtime(self):
        refs = references.load()
        assert refs.name == "gdpr"
        assert refs.origin == "gdpr.yaml (shipped)"

    def test_a_reference_without_its_wording_is_refused(self):
        with pytest.raises(ConfigError, match="has no `text:`"):
            references.parse("references:\n  x:\n    cite: X\n", origin="r.yaml")

    def test_a_field_naming_a_missing_reference_is_refused(self):
        with pytest.raises(ConfigError, match="not under `references:`"):
            references.parse(
                "references:\n  x:\n    cite: X\n    text: t\nfields:\n  purpose: y\n",
                origin="r.yaml",
            )


class TestRuleLines:
    def test_yaml_and_json_say_where_each_rule_is(self):
        text = "controller: A\njobs:\n  a/*:\n    purpose: p\n  b/*:\n    purpose: q\n"
        assert document.lines(text, origin="q.yaml", key="jobs") == {"a/*": 3, "b/*": 5}
        as_json = '{\n  "jobs": {\n    "a/*": {"purpose": "p"}\n  }\n}\n'
        assert document.lines(as_json, origin="q.json", key="jobs") == {"a/*": 3}

    def test_toml_says_none_rather_than_guessing(self):
        text = '[jobs."a/*"]\npurpose = "p"\n'
        assert document.lines(text, origin="q.toml", key="jobs") == {}
        (rule,) = config.parse(text, origin="q.toml").rules
        assert rule.line is None


class TestSignOffs:
    def test_explanations_reopen_no_sign_off(self, asserted):
        """A sign-off covers what a record states; the explanations are prose
        built from that, so adding them must not change what was signed."""
        payload = json.loads(render.json(asserted))
        without = {k: v for k, v in payload.items() if k not in ("explain", "references")}
        assert signoff.digest(payload) == signoff.digest(without)

    def test_qedro_yaml_can_point_at_another_document(self):
        assert config.parse("references: national.yaml\n").references == "national.yaml"


class TestClassificationAndTheController:
    def test_a_value_names_the_datasets_it_was_on_and_the_requirement(self, evidenced):
        a = next(a for a in evidenced.activities if a.classification)
        c = a.classification[0]
        e = explain.classification(
            a, c, references=evidenced.references, vocabulary=evidenced.vocabulary
        )
        assert e.text.startswith("The `tags` facet on ")
        assert f"`{c.key}: {c.value}`" in e.text
        assert {link.id for link in e.rests_on} >= {*c.reads, *c.writes}
        assert e.answers is not None and e.answers.cite.startswith("Art. 30(1)(")

    def test_a_value_only_another_job_carried_names_that_job(self, evidenced):
        a = next(a for a in evidenced.activities if a.classification)
        c = dataclasses.replace(a.classification[0], declared_by=("acme.other/tagger",))
        e = explain.classification(a, c, references=evidenced.references, vocabulary="v")
        assert "It came in events from `acme.other/tagger`" in e.text
        assert f"none of `{a.key}`'s own events carried it" in e.text

    def test_the_controller_points_at_its_line(self, evidenced):
        e = explain.controller(evidenced.controller, references=evidenced.references)
        (link,) = e.rests_on
        line = Path(link.file).read_text(encoding="utf-8").splitlines()[link.line - 1]
        assert line.startswith("controller:")
        assert e.answers is not None and e.answers.cite == "Art. 30(1)(a) GDPR"

    def test_a_missing_controller_is_said(self):
        refs = references.load()
        no_file = explain.controller(config.Config().controller, references=refs)
        assert no_file.text == "Nothing names a controller: there is no qedro.yaml."
        empty = explain.controller(config.parse("jobs: {}\n").controller, references=refs)
        assert empty.text == "Nothing names a controller: qedro.yaml states none."

    def test_the_json_keeps_them_apart_from_the_per_field_map(self, evidenced):
        payload = json.loads(render.json(evidenced))["explain"]
        assert all(
            isinstance(e, dict) and "text" in e
            for fields in payload["activities"].values()
            for e in fields.values()
        )
        assert payload["classification"]
        assert payload["controller"]["answers"] == "art-30-1-a"
        assert set(payload["unclassified"]) == set(evidenced.scope.unclassified)


class TestThePrintedFormats:
    def test_the_workbook_has_one_row_per_explained_value(self, asserted):
        from io import BytesIO

        from openpyxl import load_workbook

        from qedro import xlsx

        book = load_workbook(BytesIO(xlsx.workbook(asserted)))
        rows = list(book["Explanations"].iter_rows(min_row=2, values_only=True))
        assert len(rows) == len(explain.every(asserted))
        controller = rows[0]
        assert controller[1] == "Controller" and controller[4] == "Art. 30(1)(a) GDPR"
        assert all("`" not in str(row[3]) for row in rows)
        wording = {row[0]: row[1] for row in book["Requirements"].iter_rows(values_only=True)}
        assert wording["Art. 30(1)(b) GDPR"] == "the purposes of the processing;"

    def test_the_pdf_prints_the_sentences_and_the_wording(self, asserted):
        from qedro import pdf

        body = pdf.ropa_document(asserted)
        assert body.startswith(b"%PDF")
        # reportlab compresses page streams, so the text is checked on the
        # flowables that build them rather than in the bytes.
        a = asserted.activities[0]
        rows = pdf._explained(pdf._activity_rows(a), pdf._activity_whys(asserted, a))
        purpose = next(r for r in rows if r.label == "Purpose")
        assert purpose.why and "`" not in purpose.why[0]
        assert pdf._requirements(asserted)

    @pytest.mark.parametrize("fmt", ["text", "markdown"])
    def test_text_and_markdown_explain_only_when_asked(self, fmt, capsys):
        from qedro.__main__ import main

        args = ["ropa", "demo/lineage-declared", "--config", "demo/qedro.yaml", "--format", fmt]
        assert main(args) == 0
        assert "Where each value came from" not in capsys.readouterr().out
        assert main([*args, "--explain"]) == 0
        out = capsys.readouterr().out
        assert "Where each value came from" in out
        assert "Art. 30(1)(a) GDPR" in out
