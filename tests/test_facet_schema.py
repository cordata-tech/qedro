"""The published facet schema, and the tests that stop it drifting.

`schemas/openlineage-art30-processing-facet.json` is a projection of
`pipeline_runtime.descriptor.Processing`, not a second definition of it. The
published argument is that one governance model has several consumers; a
consumer that quietly restates the model is a counterexample to that argument
sitting in the repository the argument cites.

Nothing catches this automatically except a test that fails, so here is one.
The import is unconditional on purpose. A skip when `pipeline_runtime` is
absent would be a divergence check that never fires, which is worse than not
having one — `pip install -e ".[dev]"` and the CI step beside it put the
dependency there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import tools.facet_schema as generator
from pipeline_runtime.descriptor import Processing

SCHEMA = json.loads(generator.SCHEMA_PATH.read_text(encoding="utf-8"))
FIELDS = SCHEMA["allOf"][1]

FIXTURES = Path(__file__).parent / "fixtures" / "events"


class TestItIsGeneratedAndNotWritten:
    def test_the_checked_in_file_is_what_the_model_produces(self):
        # The one that matters. It fails when somebody edits either side.
        assert generator.SCHEMA_PATH.read_text(encoding="utf-8") == generator.rendered(), (
            "the schema and Processing have diverged — run `python tools/facet_schema.py`"
        )

    def test_the_check_flag_agrees(self):
        assert generator.main(["--check"]) == 0

    def test_the_file_says_it_is_generated(self):
        # A generated file that does not say so gets hand-edited eventually.
        assert "Do not edit by hand" in SCHEMA["$comment"]
        assert "Processing" in SCHEMA["$comment"]


class TestTheFieldsAreTheModelsFields:
    def test_same_properties(self):
        assert set(FIELDS["properties"]) == set(Processing.model_fields)

    def test_same_required_set(self):
        # Every field on Processing is required; if one ever becomes optional
        # the schema has to follow rather than keep claiming it is mandatory.
        assert set(FIELDS["required"]) == set(Processing.model_json_schema()["required"])

    def test_the_legal_bases_are_the_models_literal(self):
        assert FIELDS["properties"]["legal_basis"]["enum"] == list(
            Processing.model_json_schema()["properties"]["legal_basis"]["enum"]
        )

    def test_every_field_carries_prose_for_someone_outside_this_organisation(self):
        for name, spec in FIELDS["properties"].items():
            assert spec.get("description"), f"{name} has no description"

    def test_every_legal_basis_names_its_article(self):
        # An Art. 30 record that lists a basis without the Art. 6 letter makes
        # a reviewer look it up. There are six; naming them costs nothing.
        description = FIELDS["properties"]["legal_basis"]["description"]
        for value in FIELDS["properties"]["legal_basis"]["enum"]:
            assert value in description
        for letter in "abcdef":
            assert f"Art. 6(1)({letter})" in description


class TestAFieldCannotShipUndocumented:
    """The generator is the gate, so these poke the generator rather than the file."""

    def test_a_new_field_with_no_prose_stops_the_generator(self, monkeypatch):
        monkeypatch.delitem(generator.PROSE, "purpose")
        with pytest.raises(SystemExit, match="no entry in PROSE"):
            generator.build()

    def test_a_new_enum_value_with_no_prose_stops_the_generator(self, monkeypatch):
        monkeypatch.setitem(generator.VALUE_PROSE, "legal_basis", {"consent": "Art. 6(1)(a)"})
        with pytest.raises(SystemExit, match="no entry in VALUE_PROSE"):
            generator.build()


class TestItDescribesEvidenceThatExists:
    """A spec nothing emits is a wish. This one is held to the fixture."""

    def test_the_facet_key_is_the_one_real_events_carry(self):
        events = [json.loads(line) for line in _fixture_lines()]
        keys = {k for e in events for k in e.get("job", {}).get("facets", {})}
        assert generator.FACET_KEY in keys

    def test_the_emitted_facet_satisfies_the_schema_it_claims(self):
        # Not a validator pass — no jsonschema dependency for one assertion.
        # Just that what pipeline-runtime emits has the fields this document
        # says are required, and a legal basis the enum allows.
        events = [json.loads(line) for line in _fixture_lines()]
        emitted = [
            f for e in events if (f := e.get("job", {}).get("facets", {}).get(generator.FACET_KEY))
        ]
        assert emitted, "the fixture no longer carries the facet"
        for facet in emitted:
            for field in FIELDS["required"]:
                assert field in facet
            assert facet["legal_basis"] in FIELDS["properties"]["legal_basis"]["enum"]

    def test_the_schema_url_the_emitter_publishes_is_not_this_one(self):
        # Both derive from Processing; they are not the same document. The
        # runtime's `_schemaURL` points at its own repository, and this one is
        # the vendor-neutral spelling for emitters that are not it.
        events = [json.loads(line) for line in _fixture_lines()]
        urls = {
            f.get("_schemaURL")
            for e in events
            if (f := e.get("job", {}).get("facets", {}).get(generator.FACET_KEY))
        }
        assert urls and generator.SCHEMA_ID not in urls


def _fixture_lines() -> list[str]:
    path = FIXTURES / "pipeline-runtime.ndjson"
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
