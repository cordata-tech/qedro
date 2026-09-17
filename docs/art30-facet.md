# The Art. 30 processing facet

An OpenLineage job facet carrying the two fields a record of processing activities
needs and lineage does not otherwise contain: **why** the processing happens, and
**under which lawful basis**.

- Schema: [`schemas/openlineage-art30-processing-facet.json`](../schemas/openlineage-art30-processing-facet.json)
- Facet key: `processing`, in `job.facets`
- Applies to: any OpenLineage emitter, not only Cordata's

## Why it has to exist

Lineage answers *what happened*. Art. 30(1) asks a controller for a written record
that includes the **purposes of the processing** — 30(1)(b) — and, in practice, the
Art. 6(1) basis those purposes rely on. Neither is derivable from a graph of jobs and
datasets. No amount of lineage tells you whether a customer table is processed under
consent or under legitimate interest.

So it has to be declared somewhere, by someone who knows. The argument for declaring
it **on the job, in the lineage event** rather than in a separate register is that a
separate register drifts: it describes pipelines that were deleted, and omits the one
deployed last Tuesday. A facet travels with the evidence and is emitted by the thing
that ran.

A **job** facet rather than a run facet, because purpose and legal basis are
properties of the pipeline, not of one execution of it.

**What the facet does not cover.** Art. 30(1) lists seven items for a controller's
record: (a) the controller and its contacts, (b) the purposes, (c) the categories of
data subjects and of personal data, (d) the categories of recipients, (e) transfers to
third countries, (f) time limits for erasure where possible, and (g) a description of
security measures where possible. This facet carries (b). `qedro ropa` takes (a) from
`qedro.yaml`, and has no field for (c) to (g), which every record it produces says in
its scope statement. The legal basis is not one of the seven items; the facet carries it
because a purpose without the basis it relies on is of little use to the person reading
the record.

## The fields

| Field | Type | Art. |
|---|---|---|
| `purpose` | free string | 30(1)(b) |
| `legal_basis` | one of six values | 6(1)(a)–(f) |

`purpose` is deliberately not a closed set. The purposes an organisation processes
for are its own, and no vocabulary ships with the right ones.

`legal_basis` deliberately is one, because there are exactly six lawful bases and an
invented seventh reaching a generated Art. 30 record is a defect that looks like data:

| Value | Art. 6(1) |
|---|---|
| `consent` | (a) |
| `contract` | (b) |
| `legal-obligation` | (c) |
| `vital-interests` | (d) |
| `public-task` | (e) |
| `legitimate-interest` | (f) |

## Emitting it

The facet is a plain object under the `processing` key. Any emitter that can attach a
custom job facet can produce it — there is nothing Cordata-specific in the shape:

```json
{
  "job": {
    "namespace": "acme.fraud",
    "name": "transactions-scored-daily",
    "facets": {
      "processing": {
        "_producer": "https://github.com/acme/pipelines",
        "_schemaURL": "https://github.com/cordata-tech/qedro/blob/main/schemas/openlineage-art30-processing-facet.json",
        "purpose": "fraud-detection",
        "legal_basis": "legitimate-interest"
      }
    }
  }
}
```

With the OpenLineage Python client:

```python
import attr
from openlineage.client.event_v2 import Job
from openlineage.client.facet_v2 import JobFacet

SCHEMA = (
    "https://github.com/cordata-tech/qedro/blob/main/schemas/"
    "openlineage-art30-processing-facet.json"
)


@attr.define
class ProcessingJobFacet(JobFacet):
    purpose: str
    legal_basis: str

    @staticmethod
    def _get_schema() -> str:
        return SCHEMA


job = Job(
    namespace="acme.fraud",
    name="transactions-scored-daily",
    facets={"processing": ProcessingJobFacet("fraud-detection", "legitimate-interest")},
)
```

A reference emitter that already does this is
[`cordata-tech/pipeline-runtime`](https://github.com/cordata-tech/pipeline-runtime),
which reads the two fields off a pipeline descriptor and attaches them to every event
the run produces. Its `_schemaURL` points at its own repository rather than at this
one — the two documents are separate projections of the same model, not one document
with two homes.

## What Qedro does with it

`qedro ropa` reads `processing` off each job and produces the Art. 30 record from it.
That is the path where the artefact stands on its own evidence, and it is the only
path that earns the tombstone. Where the facet is absent, a purpose can be supplied by
a mapping file instead — and the run then **withholds the mark**, because a purpose
that came from a configuration file is an assertion rather than a proof. Withholding
is the signal; see the [README](../README.md#the-name).

Emitters that produce OpenLineage but not this facet — dbt, Airflow, Spark, Flink,
Dagster — work either way. Richer facets produce a richer record, and the difference
is visible in the output rather than hidden in it.

## Where the schema comes from

The schema file is **generated**, not written:

```console
$ python tools/facet_schema.py --check
schemas/openlineage-art30-processing-facet.json is current
```

Its fields, types, enum values and required set come from
`pipeline_runtime.descriptor.Processing` — the same model the reference runtime
validates descriptors against. `tests/test_facet_schema.py` fails when the two
diverge, so the document cannot quietly become a second, disagreeing definition of
the same thing. Only the prose is written here, and a field with no prose stops the
generator rather than shipping undocumented.
