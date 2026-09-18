"""The vocabulary, and the one test that stops it becoming a second definition.

The shipped `dsgvo.yaml` lists the six Art. 6(1) bases. So does the generated
facet schema. Those are two documents saying the same thing, which is exactly
the arrangement `tools/facet_schema.py` exists to prevent between Qedro and
`pipeline_runtime.descriptor` — so it needs the same guard one level down.

It is a test rather than an import on purpose. Importing the schema's enum into
`qedro.vocabulary` would make the vocabulary compiled-against rather than
loaded, which is the commitment the module exists to keep.
"""

from __future__ import annotations

import json

import pytest
import tools.facet_schema as generator

from qedro import vocabulary
from qedro.errors import ConfigError

SCHEMA = json.loads(generator.SCHEMA_PATH.read_text(encoding="utf-8"))
SCHEMA_BASES = SCHEMA["allOf"][1]["properties"]["legal_basis"]["enum"]


class TestTheShippedVocabularyAgreesWithThePublishedSchema:
    def test_same_lawful_bases(self):
        shipped = vocabulary.load().term("legal_basis")
        assert shipped is not None
        assert sorted(shipped.values) == sorted(SCHEMA_BASES), (
            "the shipped vocabulary and the published facet schema disagree about "
            "the Art. 6(1) bases — they are two projections of one law and must match"
        )

    def test_every_basis_names_its_article(self):
        shipped = vocabulary.load().term("legal_basis")
        assert shipped is not None
        for value, meaning in shipped.values.items():
            assert "Art. 6(1)(" in meaning, f"{value} does not name its article"


class TestClosedAndOpenTerms:
    def test_legal_basis_is_closed_because_the_law_closed_it(self):
        term = vocabulary.load().term("legal_basis")
        assert term is not None and term.closed

    def test_purpose_is_open_because_an_organisations_purposes_are_its_own(self):
        term = vocabulary.load().term("purpose")
        assert term is not None and not term.closed

    def test_an_invented_basis_is_surfaced(self):
        assert vocabulary.load().unrecognised("legal_basis", "vibes")

    def test_an_unlisted_purpose_is_not(self):
        # Flagging every purpose would train a reader to ignore the flag.
        assert not vocabulary.load().unrecognised("purpose", "anything-at-all")

    def test_a_term_the_vocabulary_never_heard_of_is_not_a_finding(self):
        # Silence is not prohibition. An ontology that omits a key has not
        # forbidden it, and reading it that way would make every partial
        # vocabulary look hostile.
        assert not vocabulary.load().unrecognised("residency", "eu-central-1")


class TestItIsAReplaceableDocument:
    """The commitment: data the tool loads, never types it is compiled against."""

    def test_an_organisation_can_bring_its_own(self, tmp_path):
        path = tmp_path / "house.yaml"
        path.write_text(
            "name: house-rules\n"
            "terms:\n"
            "  legal_basis:\n"
            "    closed: true\n"
            "    values:\n"
            "      einwilligung: {means: Art. 6(1)(a)}\n",
            encoding="utf-8",
        )
        loaded = vocabulary.load(path)
        assert loaded.name == "house-rules"
        # The shipped set is gone entirely — replaced, not merged. Merging would
        # mean an organisation could not remove a term it disagrees with.
        assert loaded.unrecognised("legal_basis", "consent")
        assert not loaded.unrecognised("legal_basis", "einwilligung")

    def test_a_vocabulary_can_be_json_or_toml_too(self, tmp_path):
        as_json = tmp_path / "v.json"
        as_json.write_text(
            '{"name": "j", "terms": {"legal_basis": {"closed": true, '
            '"values": {"consent": "Art. 6(1)(a)"}}}}',
            encoding="utf-8",
        )
        assert vocabulary.load(as_json).unrecognised("legal_basis", "contract")

        as_toml = tmp_path / "v.toml"
        as_toml.write_text(
            'name = "t"\n[terms.legal_basis]\nclosed = true\n'
            '[terms.legal_basis.values]\nconsent = "Art. 6(1)(a)"\n',
            encoding="utf-8",
        )
        assert vocabulary.load(as_toml).name == "t"

    def test_a_bare_value_with_no_gloss_is_allowed(self):
        # The format must not be fussier than the thing it describes.
        loaded = vocabulary.parse("name: v\nterms:\n  k:\n    values:\n      a:\n")
        term = loaded.term("k")
        assert term is not None and term.knows("a")


class TestWhatTheUserWroteRaises:
    """Evidence is counted; a document the user wrote raises."""

    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigError, match="cannot read"):
            vocabulary.load(tmp_path / "nope.yaml")

    def test_not_yaml(self, tmp_path):
        path = tmp_path / "v.yaml"
        path.write_text("name: [unclosed\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            vocabulary.load(path)

    def test_no_name(self):
        with pytest.raises(ConfigError, match="no `name`"):
            vocabulary.parse("terms: {}\n")

    def test_empty(self):
        with pytest.raises(ConfigError, match="empty"):
            vocabulary.parse("")


class TestTheArt30ClassificationTerms:
    """The terms v0.3 reports Art. 30(1)(c), (e) and (f) from. See #13."""

    def test_special_category_is_closed_on_the_art_9_list(self):
        # Art. 9(1) enumerates exactly these. A tenth value reaching a record is
        # the same defect as a seventh legal basis, so the term is closed.
        term = vocabulary.load().term("special_category")
        assert term is not None and term.closed
        assert set(term.values) == {
            "racial-or-ethnic-origin",
            "political-opinions",
            "religious-or-philosophical-beliefs",
            "trade-union-membership",
            "genetic",
            "biometric",
            "health",
            "sex-life-or-orientation",
        }
        assert term.unrecognised("shoe-size")

    def test_data_category_is_open_because_the_categories_are_the_organisation_s(self):
        words = vocabulary.load()
        term = words.term("data_category")
        assert term is not None and not term.closed
        # An insurer's own category is not a finding, the way an unlisted
        # purpose is not.
        assert not term.unrecognised("policyholder-claims")
        # Health is Art. 9 data and belongs to the closed term, so that a record
        # cannot claim special-category processing from an open list.
        assert "health" not in term.values
        assert "health" in (words.term("special_category") or term).values

    def test_the_reference_ontology_keys_are_all_present(self):
        # platform#29 settled these. `domain` is deliberately absent: it is a
        # grant and scoping key, not an Art. 30 field.
        words = vocabulary.load()
        for key in ("data_category", "special_category", "subject_type", "residency", "retention"):
            assert words.term(key) is not None, key
        assert words.term("domain") is None

    def test_every_value_says_what_it_means(self):
        # A vocabulary that lists values without saying what they imply is a
        # dropdown, not an ontology.
        words = vocabulary.load()
        for key in ("data_category", "special_category", "subject_type", "residency", "retention"):
            term = words.term(key)
            assert term is not None
            for value in term.values:
                assert (term.means(value) or "").strip(), f"{key}/{value} says nothing"
