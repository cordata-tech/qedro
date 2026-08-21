"""Generate the Art. 30 processing facet schema from the descriptor model.

The published argument is that one governance model has several consumers — CI,
the executor, the catalog server. Qedro is the fourth. A fourth consumer that
*derives* from `pipeline_runtime.descriptor.Processing` is evidence for that
claim; a fourth that restates it in a hand-written JSON file is a published
counterexample to it, and would drift within a release or two. Whoever changes
`Processing` should not also have to remember this repository exists.

So the structure here — which fields, which types, which enum values, which are
required — is read off the model. What is written by hand is the prose for an
audience the model does not have: somebody implementing the facet in a pipeline
that has never heard of Cordata. A field with no prose is a hard error rather
than an undocumented property, so a new field on `Processing` cannot reach the
published spec without someone saying what it means.

    python tools/facet_schema.py            # write schemas/…json
    python tools/facet_schema.py --check    # fail if it is out of date

`tests/test_facet_schema.py` runs the same comparison, so the divergence shows
up in CI whether or not anyone remembers this script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pipeline_runtime.descriptor import Processing

REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO / "schemas" / "openlineage-art30-processing-facet.json"

#: The key this facet occupies in a RunEvent's `job.facets`. Not derived from
#: anything: it is the wire name `pipeline-runtime` already emits and this
#: repository's fixtures already carry, so changing it would break the reader
#: against real evidence. `tests/test_facet_schema.py` holds it to the fixture.
FACET_KEY = "processing"

SCHEMA_ID = (
    "https://github.com/cordata-tech/qedro/blob/main/schemas/"
    "openlineage-art30-processing-facet.json"
)

#: Every OpenLineage job facet is a JobFacet first. The `allOf` is what carries
#: `_producer` and `_schemaURL` without this document restating them.
JOB_FACET = "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/JobFacet"

TITLE = "ProcessingJobFacet"

DESCRIPTION = (
    "DSGVO Art. 30 fields for one processing activity, carried on the job that "
    "performs it. A job facet rather than a run facet: purpose and legal basis "
    "are properties of the pipeline, not of one execution of it. Occupies the "
    f"`{FACET_KEY}` key in `job.facets`."
)

#: Prose for an implementer who has never seen the descriptor model. Keyed by
#: field name, and a field missing from here stops the generator.
PROSE = {
    "purpose": (
        "Why the processing happens, in the controller's own words. Art. 30(1)(b). "
        "Free text rather than a closed set, because the purposes an organisation "
        "processes for are its own and no vocabulary ships with the right ones."
    ),
    "legal_basis": (
        "The Art. 6(1) lawful basis for the processing. A closed set rather than a "
        "free string, so that an invented basis cannot reach a generated record of "
        "processing activities."
    ),
}

#: Prose for individual enum values, appended to the field description. A value
#: with no entry stops the generator, so extending the enum upstream cannot
#: quietly ship an undocumented one.
VALUE_PROSE = {
    "legal_basis": {
        "consent": "Art. 6(1)(a)",
        "contract": "Art. 6(1)(b)",
        "legal-obligation": "Art. 6(1)(c)",
        "vital-interests": "Art. 6(1)(d)",
        "public-task": "Art. 6(1)(e)",
        "legitimate-interest": "Art. 6(1)(f)",
    }
}

EXAMPLES = {
    "purpose": "fraud-detection",
    "legal_basis": "legitimate-interest",
}


def _property(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    """One property, structure from the model and prose from above."""
    if name not in PROSE:
        raise SystemExit(
            f"{name!r} is a field on Processing with no entry in PROSE. "
            f"Say what it means in {Path(__file__).name} before it is published."
        )

    # `title` is pydantic turning `legal_basis` into `Legal Basis`, which tells a
    # reader nothing they cannot see in the key.
    out = {k: v for k, v in spec.items() if k != "title"}
    description = PROSE[name]

    enum = out.get("enum")
    if enum:
        values = VALUE_PROSE.get(name, {})
        undocumented = [v for v in enum if v not in values]
        if undocumented:
            raise SystemExit(
                f"{name!r} has enum values with no entry in VALUE_PROSE: {', '.join(undocumented)}"
            )
        description += " Values: " + "; ".join(f"{v} — {values[v]}" for v in enum) + "."

    out["description"] = description
    if name in EXAMPLES:
        out["examples"] = [EXAMPLES[name]]
    return out


def build() -> dict[str, Any]:
    """The schema document, as it should be on disk."""
    model = Processing.model_json_schema()

    fields = {name: _property(name, spec) for name, spec in model["properties"].items()}

    # `additionalProperties: false` comes off the model, where `extra="forbid"`
    # is right: a descriptor with a misspelled field should be rejected. It is
    # wrong here. Every OpenLineage facet carries `_producer` and `_schemaURL`,
    # so a facet schema that forbids extra properties rejects every facet that
    # was ever actually emitted, including this repository's own fixtures.
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "$comment": (
            "Generated from pipeline_runtime.descriptor.Processing by "
            "tools/facet_schema.py. Do not edit by hand — the model is the source "
            "of truth and this file is a projection of it."
        ),
        "title": TITLE,
        "description": DESCRIPTION,
        "type": "object",
        "allOf": [
            {"$ref": JOB_FACET},
            {
                "type": "object",
                "properties": fields,
                "required": list(model["required"]),
            },
        ],
    }


def rendered() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Art. 30 processing facet schema from the descriptor model."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the checked-in schema is not what the model produces",
    )
    args = parser.parse_args(argv)

    want = rendered()
    if args.check:
        have = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
        if have == want:
            print(f"{SCHEMA_PATH.relative_to(REPO)} is current")
            return 0
        print(
            f"{SCHEMA_PATH.relative_to(REPO)} does not match Processing — "
            f"run `python {Path(__file__).relative_to(REPO)}`",
            file=sys.stderr,
        )
        return 1

    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(want, encoding="utf-8")
    print(f"wrote {SCHEMA_PATH.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
