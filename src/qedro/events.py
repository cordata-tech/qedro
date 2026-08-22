"""The OpenLineage event model, as much of it as the projections need.

Deliberately shallow. OpenLineage is an open spec with a long tail of facets,
and every emitter — dbt, Airflow, Spark, Flink, Dagster, this project's own
reference runtime — populates a different subset of it. Modelling every facet
would mean tracking all of them forever and breaking whenever one moves.

So the core fields are typed, because every emitter produces them and the
projections index on them, and **facets are kept as raw dictionaries**. A
projection that wants ``processing`` asks for it and copes with its absence;
a facet nobody has written a projection for still arrives intact.

The other rule here is that parsing never raises on bad input. A directory of
production lineage will contain events from emitters that disagree with the
spec, and a run that dies on the first of them is useless. Malformed events
are skipped and counted, and the count reaches the summary — see
:mod:`qedro.mark` for why that matters more than it sounds.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

#: Event types the spec defines. Anything else is passed through rather than
#: rejected: the spec has gained types before and will again, and a reader
#: that refuses unknown ones dies on somebody else's upgrade.
KNOWN_EVENT_TYPES = frozenset({"START", "RUNNING", "COMPLETE", "ABORT", "FAIL", "OTHER"})


@dataclass(frozen=True)
class Dataset:
    """One side of a job's edge — an input or an output.

    Two kinds of facet, kept apart because they answer different questions.
    ``facets`` describes the dataset itself and is true whoever is looking:
    its schema, where it lives. ``input_facets`` and ``output_facets`` describe
    **this run's use of it** — what one job asserted about it on one day.

    Merging them would be convenient and wrong. *This table has a unique
    `tx_id`* is a property of the table; *the run on the 14th checked that
    `tx_id` was unique and it held* is an event. The second is evidence and
    the first is a claim, which is the distinction the whole project turns on.
    """

    namespace: str
    name: str
    facets: Mapping[str, Any] = field(default_factory=dict)
    input_facets: Mapping[str, Any] = field(default_factory=dict)
    output_facets: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Stable identity across events. Namespace matters: two warehouses
        can hold a `customer` table and they are not the same dataset."""
        return f"{self.namespace}/{self.name}"

    def facet(self, name: str) -> Mapping[str, Any] | None:
        """A facet of the dataset itself."""
        return _facet(self.facets, name)

    def run_facet(self, name: str) -> Mapping[str, Any] | None:
        """A facet of this run's use of the dataset.

        Only one of the two sides is ever populated for a given dataset — it
        arrived as an input or as an output — so this asks both rather than
        making every caller know which.
        """
        found = _facet(self.input_facets, name)
        return found if found is not None else _facet(self.output_facets, name)

    def field_names(self) -> list[str]:
        """Column names from the standard schema facet, or empty.

        Empty means *not reported*, never *no columns* — the distinction
        matters to a projection deciding whether it can claim completeness.
        """
        fields = self.facets.get("schema", {}).get("fields", [])
        return [f["name"] for f in fields if isinstance(f, dict) and "name" in f]


@dataclass(frozen=True)
class Job:
    namespace: str
    name: str
    facets: Mapping[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.namespace}/{self.name}"


@dataclass(frozen=True)
class Run:
    run_id: str
    facets: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Event:
    """One OpenLineage RunEvent.

    ``event_time`` is a :class:`datetime` when it parsed and ``None`` when it
    did not. Emitters disagree about timezone suffixes and fractional seconds,
    and a projection filtering by date would rather see None and say so than
    receive a silently wrong instant.
    """

    event_type: str
    event_time: datetime | None
    run: Run
    job: Job
    inputs: tuple[Dataset, ...] = ()
    outputs: tuple[Dataset, ...] = ()
    producer: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def datasets(self) -> tuple[Dataset, ...]:
        return self.inputs + self.outputs

    def job_facet(self, name: str) -> Mapping[str, Any] | None:
        return _facet(self.job.facets, name)

    def run_facet(self, name: str) -> Mapping[str, Any] | None:
        return _facet(self.run.facets, name)


def _facet(facets: Mapping[str, Any], name: str) -> Mapping[str, Any] | None:
    """A facet with OpenLineage's bookkeeping keys removed.

    Every facet carries ``_producer`` and ``_schemaURL``. They are useful for
    provenance and noise everywhere else, so callers asking for a facet by
    name get the payload rather than the envelope.
    """
    raw = facets.get(name)
    if not isinstance(raw, Mapping):
        return None
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        # 3.11+ fromisoformat accepts the `Z` suffix and fractional seconds,
        # which covers what emitters actually produce. The project floor is
        # 3.12, so no normalising is needed before it.
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _datasets(raw: Any) -> tuple[Dataset, ...]:
    if not isinstance(raw, list):
        return ()
    out = []
    for d in raw:
        if not isinstance(d, Mapping):
            continue
        name, namespace = d.get("name"), d.get("namespace")
        if not isinstance(name, str) or not isinstance(namespace, str):
            continue  # a dataset without identity cannot be joined to anything
        out.append(
            Dataset(
                namespace,
                name,
                _mapping(d.get("facets")),
                # Dropped until the quality projection needed them, which is
                # how `dataQualityAssertions` went missing: it is an *input*
                # facet, not a dataset facet, and nothing was reading that side.
                _mapping(d.get("inputFacets")),
                _mapping(d.get("outputFacets")),
            )
        )
    return tuple(out)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def parse_event(raw: Any) -> Event | None:
    """Parse one event, or return None if it is not usable.

    None rather than an exception: the caller is iterating a directory that
    may hold thousands of events from several emitters, and one bad record is
    a fact to count, not a reason to stop.

    An event needs an ``eventType`` and a job identity to be worth anything —
    without a job there is nothing to attribute the work to. A missing
    ``runId`` is tolerated because some emitters omit it on OTHER events.
    """
    if not isinstance(raw, Mapping):
        return None

    event_type = raw.get("eventType")
    if not isinstance(event_type, str):
        return None

    job_raw = raw.get("job")
    if not isinstance(job_raw, Mapping):
        return None
    job_name, job_namespace = job_raw.get("name"), job_raw.get("namespace")
    if not isinstance(job_name, str) or not isinstance(job_namespace, str):
        return None

    # Bound to a name before the isinstance check so the narrowing sticks;
    # `raw.get("run") if isinstance(raw.get("run"), ...)` calls get twice and
    # a type checker cannot know the two calls agree.
    run_candidate = raw.get("run")
    run_raw: Mapping[str, Any] = run_candidate if isinstance(run_candidate, Mapping) else {}
    run_id = run_raw.get("runId")

    job_facets = job_raw.get("facets")
    run_facets = run_raw.get("facets")
    producer = raw.get("producer")

    return Event(
        event_type=event_type.upper(),
        event_time=_datetime(raw.get("eventTime")),
        run=Run(
            run_id=run_id if isinstance(run_id, str) else "",
            facets=run_facets if isinstance(run_facets, Mapping) else {},
        ),
        job=Job(
            namespace=job_namespace,
            name=job_name,
            facets=job_facets if isinstance(job_facets, Mapping) else {},
        ),
        inputs=_datasets(raw.get("inputs")),
        outputs=_datasets(raw.get("outputs")),
        producer=producer if isinstance(producer, str) else None,
        raw=raw,
    )
