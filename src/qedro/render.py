"""Turning a :class:`~qedro.ropa.Record` into something a person receives.

Four formats — text for a terminal, markdown for a repository or a document,
json for whatever consumes this next, and xlsx for the auditor, who asks for a
spreadsheet and will not be talked out of it. The first three are strings; xlsx
is bytes and lives in its own module, because a workbook is layout as well as
content and mixing that in here would bury the two rules below.

**Each format is one function that dispatches on the artefact it is given.**
`ropa` and `quality` are different records and want different tables, but they
share a scope statement, a mark and a set of reasons — and the rules below are
about exactly those. A second registry per projection would have let four
formats times three projections drift into twelve slightly different
summaries; `singledispatch` keeps the shared parts shared and the tests
parametrised over both axes.

**Every format prints the scope statement**, and none of them may make it
conditional. A renderer that skips it on a clean run has quietly taught the
reader that its absence means full coverage. See cordata-tech/qedro#3.

The other rule: **provenance survives rendering.** Every format has to make it
possible to tell an evidenced entry from an asserted one. A format that flattens
the two has thrown away the only thing that makes this record different from one
a person typed.
"""

from __future__ import annotations

import json as _json
from collections.abc import Iterable
from datetime import datetime
from functools import singledispatch

from . import TOMBSTONE, words
from . import deployer as deployer_module
from . import provenance as provenance_module
from . import quality as quality_module
from .ropa import ART30_ASSERTED_ONLY, ART30_COVERED, ART30_ITEMS, Activity, Record
from .scope import Scope

#: What each provenance looks like in a rendered table. The evidenced case gets
#: no decoration: it is the normal case, and marking it would make the record
#: look like it was arguing with itself.
BADGE = {
    "facet": "",
    "mapping": " (mapping)",
    "declared": " (declared)",
    "absent": "",
}


def _when(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def _field(sourced) -> str:
    if not sourced.value:
        return "— not declared"
    flag = " ⚠ not in vocabulary" if sourced.unrecognised else ""
    return f"{sourced.value}{BADGE.get(str(sourced.provenance), '')}{flag}"


@singledispatch
def text(record: object, *, symbol: bool = True, width: int = 88) -> str:
    """The terminal rendering. Dense, and readable without scrolling."""
    raise TypeError(f"no text rendering for {type(record).__name__}")


@text.register
def _(record: Record, *, symbol: bool = True, width: int = 88) -> str:
    out: list[str] = []
    controller = record.controller.name or "no controller declared"
    out.append(f"Record of processing activities — {controller}")
    if record.controller.contact:
        out.append(f"  contact: {record.controller.contact}")
    out.append("")

    for activity in record.activities:
        out.append(f"  {activity.key}")
        out += _detail("purpose", _field(activity.purpose), width=width)
        out += _detail("legal basis", _field(activity.legal_basis), width=width)
        out.extend(_classification_text(activity, width=width))
        if activity.inputs:
            out += _detail("reads", ", ".join(activity.inputs), width=width)
        if activity.outputs:
            out += _detail("writes", ", ".join(activity.outputs), width=width)
        out += _detail(
            "runs", f"{activity.runs} in window, last {_when(activity.last_seen)}", width=width
        )
        out.append("")

    for entry in record.declared:
        domain = f"  ({entry.domain})" if entry.domain else ""
        out.append(f"  {entry.name}{domain}  — declared, no lineage")
        out.append(f"    purpose       {_field(entry.purpose)}")
        out.append(f"    legal basis   {_field(entry.legal_basis)}")
        # "no lineage" rather than a blank or 0: a blank reads as *touches no
        # data* and 0 as *ran zero times*, and neither is known.
        reads = (
            f"no lineage — declared: {', '.join(entry.inputs)}" if entry.inputs else "no lineage"
        )
        out.append(f"    reads         {reads}")
        out.append("    writes        no lineage")
        out.append("    runs          no lineage")
        if entry.recipients:
            out += _detail("recipients", f"{'; '.join(entry.recipients)} (declared)", width=width)
        if entry.security_measures:
            out += _detail(
                "security", f"{'; '.join(entry.security_measures)} (declared)", width=width
            )
        if entry.note:
            out.append(f"    note          {entry.note}")
        out.append("")

    out.extend(_scope_text(record.scope, width=width))
    out.append("")
    out.extend(_verdict_text(record, "every activity stands on emitted evidence", symbol=symbol))

    return "\n".join(out) + "\n"


#: What each classification key is called in the output, in Art. 30(1) order.
#: The label says what the value answers rather than repeating the tag key: a
#: reader of the record has not read the vocabulary.
CLASSIFICATION_LABELS = (
    ("data_category", "categories"),
    ("special_category", "special"),
    ("subject_type", "subjects"),
    ("residency", "residency"),
    ("retention", "retention"),
)


def _classification_text(activity: Activity, *, width: int) -> list[str]:
    """The classification lines for one activity, and what was not classified."""
    out: list[str] = []
    for key, label in CLASSIFICATION_LABELS:
        found = [c for c in activity.classification if c.key == key]
        if not found:
            continue
        values = ", ".join(
            f"{c.value}{' ⚠ not in vocabulary' if c.unrecognised else ''}" for c in found
        )
        out += _detail(label, values, width=width)
    for values, label in (
        (activity.recipients, "recipients"),
        (activity.security_measures, "security"),
    ):
        if values:
            # Semicolons, because a recipient is a phrase and phrases contain
            # commas: *the card scheme, for disputed transactions* is one
            # recipient, and a comma-joined list would read as two.
            #
            # `(declared)` on every one: nothing emits these, so an unmarked
            # value would read as evidence the record does not have.
            out += _detail(label, f"{'; '.join(values)} (declared)", width=width)
    if activity.unclassified:
        total = len(set(activity.inputs) | set(activity.outputs))
        n = len(activity.unclassified)
        out += _detail(
            "unclassified",
            f"{n} of {total} {words.plural(total, 'dataset', 'datasets')} "
            f"{words.plural(n, 'carries', 'carry')} "
            f"no classification: {', '.join(activity.unclassified)}",
            width=width,
        )
    return out


#: Where a label ends and its value begins, in the activity block and the scope
#: statement alike.
LABEL = 13
INDENT = " " * (4 + LABEL + 1)


def _detail(label: str, value: str, *, width: int) -> list[str]:
    """One labelled line of an activity, wrapped under the value.

    A dataset list or a set of recipients runs past a terminal otherwise, and
    the reader who most needs these lines is reading them in a terminal.
    """
    wrapped = _wrap(value, width - len(INDENT)) or [""]
    return [f"    {label:<{LABEL}} {wrapped[0]}"] + [f"{INDENT}{line}" for line in wrapped[1:]]


def _scope_text(scope: Scope, *, width: int, title: str = "Scope of this record") -> list[str]:
    """Shared by every projection. The labels come from the scope itself."""
    out = [f"  {title}", f"    source        {scope.source or 'unknown'}"]
    out.append(f"    window        {scope.window()}")
    rows = list(scope.lines())
    if scope.domains_source():
        rows.append(("domains", scope.domains_source()))
    if scope.domains_silent:
        rows.append(("silent", f"{', '.join(scope.domains_silent)} (in scope, no lineage)"))
    # Wrapped under the value, not the label: the parents and Art. 30(1) lines
    # run far past a terminal's width otherwise.
    for label, value in rows:
        out += _detail(label, value, width=width)
    for line in _wrap(scope.OUT_OF_VIEW, width - 4):
        out.append(f"    {line}")
    return out


def _verdict_text(record, earned: str, *, symbol: bool, withheld: str = "record") -> list[str]:
    """The mark, or the reasons it was withheld. Never a bare boolean."""
    if record.complete:
        return [f"  {earned}   {TOMBSTONE if symbol else '[complete]'}"]
    return [f"  this {withheld} does not claim to be a proof:"] + [
        f"    ! {reason}" for reason in record.completeness.reasons
    ]


def _wrap(paragraph: str, width: int) -> list[str]:
    words, lines, current = _citations(paragraph.split()), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _citations(words: list[str]) -> list[str]:
    """Keep `Art.` with the article it cites, so a wrap cannot separate them.

    A line ending in `Art.` with `30(1)(a)` beginning the next reads as two
    different things, and a reader checking a legal reference is exactly the
    reader who cannot afford that.
    """
    out: list[str] = []
    for word in words:
        if out and out[-1].endswith("Art."):
            out[-1] = f"{out[-1]} {word}"
        else:
            out.append(word)
    return out


@singledispatch
def markdown(record: object) -> str:
    """For a repository, a wiki, or a document somebody prints."""
    raise TypeError(f"no markdown rendering for {type(record).__name__}")


@markdown.register
def _(record: Record) -> str:
    controller = record.controller.name or "_no controller declared_"
    out = [f"# Record of processing activities — {controller}", ""]
    if record.controller.contact:
        out += [f"**Contact:** {record.controller.contact}", ""]

    out += [
        (
            "| Activity | Purpose | Legal basis | Source | Recipients | Security measures "
            "| Reads | Writes | Runs |"
        ),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for a in record.activities:
        out.append(
            f"| `{a.key}` | {a.purpose.value or '—'} | {a.legal_basis.value or '—'} "
            f"| {_provenance_cell(a)} | {_asserted(a.recipients)} "
            f"| {_asserted(a.security_measures)} "
            f"| {len(a.inputs)} | {len(a.outputs)} | {a.runs} |"
        )
    for d in record.declared:
        out.append(
            f"| `{d.name}` | {d.purpose.value or '—'} | {d.legal_basis.value or '—'} "
            f"| **declared, no lineage** | {_asserted(d.recipients)} "
            f"| {_asserted(d.security_measures)} "
            "| no lineage | no lineage | no lineage |"
        )

    out += _classification_markdown(record)
    out += _scope_markdown(record.scope)
    out += _verdict_markdown(record, "Every activity in this record stands on emitted evidence.")

    return "\n".join(out)


def _classification_markdown(record: Record) -> list[str]:
    """Classification in a table of its own.

    Six more columns on the record table would make it unreadable, and this
    answers a different question: the record table says what an activity does,
    this says what the data it touched is.
    """
    if not any(a.classification or a.unclassified for a in record.activities):
        return []

    out = [
        "",
        "## What the data is",
        "",
        "| Activity | Categories | Special category | Subjects | Residency | Retention | Unclassified |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in record.activities:
        cells = [
            ", ".join(
                f"{c.value}{' ⚠' if c.unrecognised else ''}"
                for c in a.classification
                if c.key == key
            )
            or "—"
            for key, _ in CLASSIFICATION_LABELS
        ]
        unclassified = f"{len(a.unclassified)} datasets" if a.unclassified else "—"
        out.append(f"| `{a.key}` | {' | '.join(cells)} | {unclassified} |")
    return out


def _scope_markdown(scope: Scope, *, title: str = "Scope of this record") -> list[str]:
    out = ["", f"## {title}", ""]
    out += [
        f"- **Source** — {scope.source or 'unknown'}",
        f"- **Window** — {scope.window()}",
    ]
    out += [f"- **{label[0].upper()}{label[1:]}** — {value}" for label, value in scope.lines()]
    if scope.domains_source():
        out.append(f"- **Domains** — {scope.domains_source()}")
    if scope.domains_silent:
        out.append(f"- **Declared in scope but silent** — {', '.join(scope.domains_silent)}")
    return out + ["", scope.OUT_OF_VIEW, ""]


def _verdict_markdown(record, earned: str, *, withheld: str = "record") -> list[str]:
    if record.complete:
        return [f"{earned} {TOMBSTONE}", ""]
    return (
        [f"**This {withheld} does not claim to be a proof.**", ""]
        + [f"- {reason}" for reason in record.completeness.reasons]
        + [""]
    )


def _asserted(values: tuple[str, ...]) -> str:
    """Art. 30(1)(d) or (g) in a table cell, always marked as an assertion.

    Nothing emits either, so there is no evidenced case to distinguish this
    from — which is exactly why it has to say so rather than look like the
    columns beside it.
    """
    return f"{', '.join(values)} _(declared)_" if values else "—"


def _provenance_cell(activity: Activity) -> str:
    sources = {str(activity.purpose.provenance), str(activity.legal_basis.provenance)}
    if sources == {"facet"}:
        return "emitted facet"
    if "mapping" in sources:
        return "mapping file"
    return "not declared"


@singledispatch
def json(record: object, *, indent: int = 2) -> str:
    """For whatever consumes this next.

    Provenance is a field per value rather than a summary, so a consumer can
    make the evidenced/asserted distinction without re-deriving it.

    Deliberately *not* generated from `scope.lines()`: those labels are prose
    for a reader, and a machine consumer needs the numbers separately rather
    than a sentence to parse back apart.
    """
    raise TypeError(f"no json rendering for {type(record).__name__}")


@json.register
def _(record: Record, *, indent: int = 2) -> str:
    payload = {
        "controller": {
            "name": record.controller.name,
            "contact": record.controller.contact,
            "representative": record.controller.representative,
            "dpo": record.controller.dpo,
        },
        "vocabulary": record.vocabulary,
        "activities": [_activity_json(a) for a in record.activities],
        "declared": [_declared_json(d) for d in record.declared],
        "scope": {
            "source": record.scope.source,
            "window": {
                "since": _when(record.scope.since),
                "until": _when(record.scope.until),
            },
            "events": record.scope.events,
            "jobs": record.scope.jobs,
            "parents": list(record.scope.parents),
            "read_only": list(record.scope.read_only),
            "declared": record.scope.declared,
            "datasets": record.scope.datasets,
            "namespaces": list(record.scope.namespaces),
            "domains_declared": list(record.scope.domains_declared),
            "domains_seen": list(record.scope.domains_seen),
            "domains_guessed": list(record.scope.domains_guessed),
            "domains_mapped": list(record.scope.domains_mapped),
            "domains_silent": list(record.scope.domains_silent),
            # Letters rather than the sentence, so a consumer does not parse prose.
            "art30": {
                "covered": [k for k, _ in ART30_ITEMS if k in ART30_COVERED],
                "not_covered": [k for k, _ in ART30_ITEMS if k not in ART30_COVERED],
                # How many activities report a value for each item, out of how
                # many there are. A field with no values is still a field.
                "reported": dict(sorted(record.scope.reported.items())),
                "activities": record.scope.activities,
                # Items nothing emits, so a value for one of these is always an
                # assertion. A consumer weighing the record should know which.
                "asserted_only": sorted(ART30_ASSERTED_ONLY),
            },
            "unclassified_datasets": list(record.scope.unclassified),
            "provenance": {
                "evidenced": record.scope.evidenced,
                "from_mapping": record.scope.from_mapping,
                "undeclared": record.scope.undeclared,
            },
            "out_of_view": record.scope.OUT_OF_VIEW,
        },
        "complete": record.complete,
        "reasons": list(record.completeness.reasons),
    }
    return _json.dumps(payload, indent=indent, ensure_ascii=False) + "\n"


def _declared_json(entry) -> dict[str, object]:
    """A declared activity. `null` where the events would have spoken, because
    nothing did — not an empty list, which would claim nothing was read."""
    return {
        "name": entry.name,
        "domain": entry.domain,
        "evidence": "declared",
        "purpose": {
            "value": entry.purpose.value,
            "provenance": str(entry.purpose.provenance),
            "unrecognised": entry.purpose.unrecognised,
        },
        "legal_basis": {
            "value": entry.legal_basis.value,
            "provenance": str(entry.legal_basis.provenance),
            "unrecognised": entry.legal_basis.unrecognised,
        },
        "model": entry.model,
        "inputs_declared": list(entry.inputs),
        "recipients": {"values": list(entry.recipients), "provenance": "declared"},
        "security_measures": {
            "values": list(entry.security_measures),
            "provenance": "declared",
        },
        "note": entry.note,
        "reads": None,
        "writes": None,
        "runs": None,
    }


def _activity_json(activity: Activity) -> dict[str, object]:
    return {
        "job": activity.key,
        "namespace": activity.namespace,
        "name": activity.name,
        "domain": activity.domain,
        "domain_source": "namespace" if activity.domain_guessed else "mapping",
        "classification": [
            {
                "key": c.key,
                "value": c.value,
                "art30_item": c.item,
                "provenance": str(c.provenance),
                "unrecognised": c.unrecognised,
                "reads": list(c.reads),
                "writes": list(c.writes),
            }
            for c in activity.classification
        ],
        # Datasets this activity touched that carry no classification the record
        # can use. Not the same as *no personal data*, and a consumer that read
        # an empty list as that would be inventing an answer.
        "unclassified": list(activity.unclassified),
        # Art. 30(1)(d) and (g). `provenance` is stated rather than implied,
        # because these can only ever be asserted.
        "recipients": {"values": list(activity.recipients), "provenance": "mapping"},
        "security_measures": {
            "values": list(activity.security_measures),
            "provenance": "mapping",
        },
        "purpose": {
            "value": activity.purpose.value,
            "provenance": str(activity.purpose.provenance),
            "unrecognised": activity.purpose.unrecognised,
        },
        "legal_basis": {
            "value": activity.legal_basis.value,
            "provenance": str(activity.legal_basis.provenance),
            "unrecognised": activity.legal_basis.unrecognised,
        },
        "reads": list(activity.inputs),
        "writes": list(activity.outputs),
        "runs": activity.runs,
        "events": activity.events,
        "first_seen": _when(activity.first_seen),
        "last_seen": _when(activity.last_seen),
        "evidenced": activity.evidenced,
        "gaps": activity.gaps(),
    }


@singledispatch
def xlsx(record: object) -> bytes:
    """The workbook, as bytes.

    openpyxl is imported inside each implementation rather than at module
    scope so that `qedro events`, and every text rendering, pays nothing for a
    format they do not produce.
    """
    raise TypeError(f"no workbook for {type(record).__name__}")


@xlsx.register
def _(record: Record) -> bytes:
    from .xlsx import workbook

    return workbook(record)


@xlsx.register
def _(record: quality_module.Record) -> bytes:
    from .xlsx import quality_workbook

    return quality_workbook(record)


#: How many unchecked datasets to name before summarising the rest. A list that
#: simply stops looks like the whole list, so the remainder is always counted.
UNCHECKED_SHOWN = 25


@text.register
def _(record: quality_module.Record, *, symbol: bool = True, width: int = 88) -> str:
    out: list[str] = []
    controller = record.controller.name or "no controller declared"
    out.append(f"Data quality assertion history — {controller}")
    out.append("")

    for dataset in record.datasets:
        domain = f"  ({dataset.domain})" if dataset.domain else ""
        out.append(f"  {dataset.key}{domain}")
        out.append(f"    asserted by   {', '.join(dataset.asserted_by)}")
        out.append(f"    runs          {dataset.runs} in window, last {_when(dataset.last_seen)}")
        held = len(dataset.expectations) - len(dataset.failing())
        out.append(
            f"    expectations  {len(dataset.expectations)} — "
            f"{held} held, {len(dataset.failing())} failed"
        )
        out.extend(f"      {line}" for line in _expectations_text(dataset))
        out.append("")

    out.extend(_unchecked_text(record))
    out.extend(_scope_text(record.scope, width=width, title="Scope of this history"))
    out.append("")
    out.extend(
        _verdict_text(
            record,
            "this history accounts for every dataset in view",
            symbol=symbol,
            withheld="history",
        )
    )

    return "\n".join(out) + "\n"


def _expectations_text(dataset) -> list[str]:
    """One line per expectation.

    Words rather than tick and cross glyphs: this file already has one
    character whose font coverage is thin, and a result nobody can read is
    worse than a longer line.
    """
    out = []
    for e in dataset.expectations:
        marker = "held  " if e.holds else "FAILED"
        detail = words.count(e.runs, "run")
        if not e.holds:
            detail += f", {e.failures} failed, last {_when(e.last_failure)}"
        out.append(f"{marker}  {e.describe:<52} {detail}")
    return out


def _unchecked_text(record: quality_module.Record) -> list[str]:
    """The half of the artefact that is about absence.

    Not a footnote. A dataset with no assertions and a dataset with no
    failures read identically in any summary, and they are opposites.
    """
    if not record.unchecked:
        return []
    out = [f"  Not checked — {len(record.unchecked)} datasets carry no assertions at all"]
    for key in record.unchecked[:UNCHECKED_SHOWN]:
        out.append(f"    {key}")
    if len(record.unchecked) > UNCHECKED_SHOWN:
        out.append(f"    … and {len(record.unchecked) - UNCHECKED_SHOWN} more")
    return out + [""]


@markdown.register
def _(record: quality_module.Record) -> str:
    controller = record.controller.name or "_no controller declared_"
    out = [f"# Data quality assertion history — {controller}", ""]

    out += [
        "| Dataset | Domain | Expectations | Runs | Failed | Last asserted |",
        "|---|---|---|---|---|---|",
    ]
    for d in record.datasets:
        out.append(
            f"| `{d.key}` | {d.domain or '—'} | {len(d.expectations)} | {d.runs} "
            f"| {len(d.failing())} | {_when(d.last_seen)} |"
        )

    if record.unchecked:
        out += ["", f"## Not checked — {len(record.unchecked)} datasets", ""]
        out += [
            (
                "These appeared in lineage and carry no assertions. "
                "**Not checked is not the same as passed.**"
            ),
            "",
        ]
        out += [f"- `{key}`" for key in record.unchecked[:UNCHECKED_SHOWN]]
        if len(record.unchecked) > UNCHECKED_SHOWN:
            out.append(f"- … and {len(record.unchecked) - UNCHECKED_SHOWN} more")

    out += _scope_markdown(record.scope)
    out += _verdict_markdown(
        record, "This history accounts for every dataset in view.", withheld="history"
    )

    return "\n".join(out)


@json.register
def _(record: quality_module.Record, *, indent: int = 2) -> str:
    payload = {
        "controller": {
            "name": record.controller.name,
            "contact": record.controller.contact,
        },
        "datasets": [
            {
                "dataset": d.key,
                "domain": d.domain,
                "asserted_by": list(d.asserted_by),
                "runs": d.runs,
                "checks": d.checks,
                "failures": d.failures,
                "holds": d.holds,
                "first_seen": _when(d.first_seen),
                "last_seen": _when(d.last_seen),
                "expectations": [
                    {
                        "assertion": e.assertion,
                        "column": e.column,
                        "runs": e.runs,
                        "failures": e.failures,
                        "holds": e.holds,
                        "first_seen": _when(e.first_seen),
                        "last_seen": _when(e.last_seen),
                        "last_failure": _when(e.last_failure),
                    }
                    for e in d.expectations
                ],
            }
            for d in record.datasets
        ],
        # A list rather than a count. The count is what a reader reacts to and
        # the names are what they act on, and a consumer needs the names.
        "unchecked": list(record.unchecked),
        "scope": {
            "source": record.scope.source,
            "window": {"since": _when(record.scope.since), "until": _when(record.scope.until)},
            "events": record.scope.events,
            "datasets": record.scope.datasets,
            "checked": record.scope.checked,
            "unchecked": record.scope.unchecked,
            "checks": record.scope.checks,
            "failures": record.scope.failures,
            "domains_filter": list(record.scope.domains_filter),
            "left_out": [
                {"domain": domain, "datasets": n, "guessed": guessed}
                for domain, n, guessed in record.scope.left_out
            ],
            "domains_declared": list(record.scope.domains_declared),
            "domains_seen": list(record.scope.domains_seen),
            "domains_guessed": list(record.scope.domains_guessed),
            "domains_mapped": list(record.scope.domains_mapped),
            "domains_silent": list(record.scope.domains_silent),
            "out_of_view": record.scope.OUT_OF_VIEW,
        },
        "complete": record.complete,
        "reasons": list(record.completeness.reasons),
    }
    return _json.dumps(payload, indent=indent, ensure_ascii=False) + "\n"


# --- provenance -------------------------------------------------------------


@text.register
def _(record: provenance_module.Record, *, symbol: bool = True, width: int = 88) -> str:
    out: list[str] = [f"Provenance of {record.dataset}", ""]

    for step in record.steps:
        indent = "  " + "  " * step.depth
        out.append(f"{indent}{step.dataset}")
        out.extend(_step_text(step, indent + "  "))
        out.append("")

    out.extend(_scope_text(record.scope, width=width, title="Scope of this chain"))
    out.append("")
    out.extend(
        _verdict_text(
            record,
            "every step ran under a signed commit",
            symbol=symbol,
            withheld="chain",
        )
    )
    return "\n".join(out) + "\n"


def _step_text(step, indent: str) -> list[str]:
    if not step.production:
        return [f"{indent}— {step.ended}"]

    p = step.production
    run = f"{p.run_id or 'unreported'} ({p.event_type.lower()}), {_when(p.when)}"
    out = [
        f"{indent}produced by   {p.job}",
        f"{indent}run           {run}",
        f"{indent}code          {p.code.describe()}",
    ]
    if p.code.branch or p.code.path:
        where = " ".join(x for x in (p.code.branch, p.code.path) if x)
        out.append(f"{indent}              {where}")
    out.append(f"{indent}signature     {p.signature.describe()}")
    if step.also_produced_by:
        out.append(
            f"{indent}also          {words.count(step.also_produced_by, 'other run')} "
            "wrote this in the window"
        )
    if step.ended:
        out.append(f"{indent}— {step.ended}")
    return out


@markdown.register
def _(record: provenance_module.Record) -> str:
    out = [f"# Provenance of `{record.dataset}`", ""]
    out += [
        "| Depth | Dataset | Produced by | Commit | Signature |",
        "|---|---|---|---|---|",
    ]
    for step in record.steps:
        if step.production:
            p = step.production
            out.append(
                f"| {step.depth} | `{step.dataset}` | `{p.job}` "
                f"| {p.code.short or '—'} | {p.signature.describe()} |"
            )
        else:
            out.append(f"| {step.depth} | `{step.dataset}` | — | — | _{step.ended}_ |")

    out += _scope_markdown(record.scope)
    out += _verdict_markdown(record, "Every step ran under a signed commit.", withheld="chain")
    return "\n".join(out)


@json.register
def _(record: provenance_module.Record, *, indent: int = 2) -> str:
    payload = {
        "dataset": record.dataset,
        "steps": [
            {
                "dataset": s.dataset,
                "depth": s.depth,
                "ended": s.ended,
                "also_produced_by": s.also_produced_by,
                "production": None
                if not s.production
                else {
                    "job": s.production.job,
                    "run_id": s.production.run_id,
                    "event_type": s.production.event_type,
                    "when": _when(s.production.when),
                    "reads": list(s.production.reads),
                    "code": {
                        "repository": s.production.code.repository,
                        "commit": s.production.code.commit,
                        "branch": s.production.code.branch,
                        "path": s.production.code.path,
                    },
                    # Three states, never two. `null` is *nobody reported*, and
                    # a consumer that read it as false would be inventing a
                    # finding the chain does not support.
                    "signed": s.production.signature.signed,
                    "signature_reported_by": s.production.signature.reported_by,
                    "authorised": s.production.authorised,
                },
            }
            for s in record.steps
        ],
        "scope": {
            "source": record.scope.source,
            "dataset": record.scope.dataset,
            "window": {"since": _when(record.scope.since), "until": _when(record.scope.until)},
            "events": record.scope.events,
            "steps": record.scope.steps,
            "with_commit": record.scope.with_commit,
            "with_signature": record.scope.with_signature,
            "ends_unproduced": record.scope.ends_unproduced,
            "ends_at_depth": record.scope.ends_at_depth,
            "depth_limit": record.scope.depth_limit,
            "out_of_view": record.scope.OUT_OF_VIEW,
        },
        "complete": record.complete,
        "reasons": list(record.completeness.reasons),
    }
    return _json.dumps(payload, indent=indent, ensure_ascii=False) + "\n"


@xlsx.register
def _(record: provenance_module.Record) -> bytes:
    from .xlsx import provenance_workbook

    return provenance_workbook(record)


# --- the deployer view -------------------------------------------------------


def _models_text(use_case) -> list[str]:
    """One line per version, then where the versions were read from.

    The source is named once rather than on every line, because it is almost
    always the same facet — and it is named at all because a version read from
    a documented facet is evidence only as far as that facet is.
    """
    width = max((len(m.version) for m in use_case.models), default=len("none reported"))
    width = max(width, len("none reported")) if use_case.runs_without_model else width
    out = []
    for m in use_case.models:
        first = m.first_seen.date() if m.first_seen else "?"
        last = m.last_seen.date() if m.last_seen else "?"
        out.append(f"{m.version:<{width}}  {words.count(m.runs, 'run'):>8}, {first} to {last}")
    if use_case.runs_without_model:
        runs = words.count(use_case.runs_without_model, "run")
        out.append(f"{'none reported':<{width}}  {runs:>8}")
    sources = sorted({m.reported_by for m in use_case.models})
    out.append(f"reported in the {', '.join(sources)} run facet")
    return out


def _retention_text(use_case) -> str:
    days = use_case.span_days
    first, last = use_case.activity.first_seen, use_case.activity.last_seen
    if days is None or first is None or last is None:
        return "no dated run records in view"
    enough = "at least six months" if days >= deployer_module.SIX_MONTHS else "less than six months"
    return (
        f"{words.count(use_case.activity.runs, 'run')}, {first.date()} to {last.date()} "
        f"({words.count(days, 'day')}) — {enough} in view"
    )


def _declared_label(entry) -> str:
    return "declared, no lineage"


#: Label column for the deployer view, so the values line up.
_LABEL = 25

#: What each Art. 26 reference is, printed under the value it sits beside. A
#: list of inputs is context for the Art. 26(4) judgement — whether input data
#: is relevant and sufficiently representative — and not evidence that anybody
#: made it; a span of records is context for Art. 26(6) and not a retention
#: policy. Putting the article in the label read as more than that.
_INPUTS_CONTEXT = "context for Art. 26(4), not a check of relevance or representativeness"
_RECORDS_CONTEXT = "context for Art. 26(6), not a retention policy or a compliance finding"


def _hang(label: str, value: str, *, width: int) -> list[str]:
    """A labelled value, wrapped under itself rather than under the label."""
    indent = " " * (4 + _LABEL)
    lines = _wrap(value, width - len(indent)) or [""]
    return [f"    {label:<{_LABEL}}{lines[0]}"] + [f"{indent}{line}" for line in lines[1:]]


@text.register
def _(record: deployer_module.DeployerRecord, *, symbol: bool = True, width: int = 88) -> str:
    controller = record.controller.name or "no controller declared"
    out = [f"AI use cases, deployer view of the Art. 30 record — {controller}", ""]
    # One line per sentence rather than one wrapped paragraph, so the wrap
    # cannot strand "Art." from "26" or "2" from "December 2027".
    for paragraph in (
        f"{record.regulation}.",
        deployer_module.APPLIES_FROM,
        deployer_module.NOT_DECIDED,
        "Purpose and legal basis are the Art. 30 record's own entries, not restated.",
    ):
        out.extend(f"  {line}" for line in _wrap(paragraph, width - 2))
    out.append("")

    indent = " " * (4 + _LABEL)
    for use_case in record.use_cases:
        a = use_case.activity
        domain = f"  ({a.domain})" if a.domain else ""
        out.append(f"  {a.key}{domain}")
        out += _hang("purpose", _field(a.purpose), width=width)
        out += _hang("legal basis", _field(a.legal_basis), width=width)
        models = _models_text(use_case)
        out.append(f"    {'model version':<{_LABEL}}{models[0]}")
        out.extend(f"{indent}{line}" for line in models[1:])
        latest = use_case.latest
        out.append(
            f"    {'latest run':<{_LABEL}}{_when(latest.when)}, "
            f"model {latest.model_version or 'none reported'}"
        )
        out.append(f"{indent}run {latest.run_id}")
        out += _hang("inputs read", ", ".join(latest.inputs) or "none reported", width=width)
        out.extend(f"{indent}{line}" for line in _wrap(_INPUTS_CONTEXT, width - len(indent)))
        out += _hang("run records", _retention_text(use_case), width=width)
        out.extend(f"{indent}{line}" for line in _wrap(_RECORDS_CONTEXT, width - len(indent)))
        out.append("")

    for entry in record.declared:
        domain = f"  ({entry.domain})" if entry.domain else ""
        out.append(f"  {entry.name}{domain}  — {_declared_label(entry)}")
        out += _hang("purpose", _field(entry.purpose), width=width)
        out += _hang("legal basis", _field(entry.legal_basis), width=width)
        out += _hang("model", f"{entry.model or 'not declared'} (declared)", width=width)
        inputs = ", ".join(entry.inputs) or "not declared"
        out += _hang("inputs read", f"{inputs} (declared)", width=width)
        out.extend(f"{indent}{line}" for line in _wrap(_INPUTS_CONTEXT, width - len(indent)))
        out += _hang("run records", "none — nothing emits lineage for this use", width=width)
        out.extend(f"{indent}{line}" for line in _wrap(_RECORDS_CONTEXT, width - len(indent)))
        if entry.note:
            out += _hang("note", entry.note, width=width)
        out.append("")

    out.extend(_scope_text(record.scope, width=width, title="Scope of this view"))
    out.append("")
    out.extend(
        _verdict_text(
            record,
            "every AI use case in view stands on emitted evidence",
            symbol=symbol,
            withheld="view",
        )
    )
    return "\n".join(out) + "\n"


@markdown.register
def _(record: deployer_module.DeployerRecord) -> str:
    controller = record.controller.name or "_no controller declared_"
    out = [
        f"# AI use cases, deployer view of the Art. 30 record — {controller}",
        "",
        f"{record.regulation}. {record.application}",
        "",
        "Purpose and legal basis are the Art. 30 record's own entries, not restated.",
        "",
        (
            "| Use case | Domain | Purpose | Legal basis | Source | Model version "
            "| Inputs read, latest run (context for Art. 26(4)) "
            "| Run records in view (context for Art. 26(6)) |"
        ),
        "|---|---|---|---|---|---|---|---|",
    ]
    for u in record.use_cases:
        a = u.activity
        versions = "; ".join(f"{m.version} ({words.count(m.runs, 'run')})" for m in u.models)
        out.append(
            f"| `{a.key}` | {a.domain or '—'} | {a.purpose.value or '—'} "
            f"| {a.legal_basis.value or '—'} | {_provenance_cell(a)} | {versions} "
            f"| {', '.join(u.latest.inputs) or '—'} | {_retention_text(u)} |"
        )
    for d in record.declared:
        out.append(
            f"| `{d.name}` | {d.domain or '—'} | {d.purpose.value or '—'} "
            f"| {d.legal_basis.value or '—'} | **{_declared_label(d)}** "
            f"| {d.model or '—'} (declared) | {', '.join(d.inputs) or '—'} (declared) "
            f"| none — no lineage |"
        )

    out += _scope_markdown(record.scope, title="Scope of this view")
    out += _verdict_markdown(
        record, "Every AI use case in this view stands on emitted evidence.", withheld="view"
    )
    return "\n".join(out)


@json.register
def _(record: deployer_module.DeployerRecord, *, indent: int = 2) -> str:
    def sourced(s) -> dict[str, object]:
        return {
            "value": s.value,
            "provenance": str(s.provenance),
            "unrecognised": s.unrecognised,
        }

    payload = {
        "view": "deployer",
        "controller": {
            "name": record.controller.name,
            "contact": record.controller.contact,
        },
        "references": {
            "regulation": record.regulation,
            "celex": "02024R1689-20260727",
            "article_26_applies_from": "2027-12-02",
            "article_26_applies_to": "deployers of high-risk AI systems listed in Annex III",
            "high_risk_decided": False,
        },
        "use_cases": [
            {
                "job": u.key,
                "domain": u.activity.domain,
                "evidence": "lineage",
                "purpose": sourced(u.activity.purpose),
                "legal_basis": sourced(u.activity.legal_basis),
                "model_versions": [
                    {
                        "version": m.version,
                        "reported_by": m.reported_by,
                        "runs": m.runs,
                        "first_seen": _when(m.first_seen),
                        "last_seen": _when(m.last_seen),
                    }
                    for m in u.models
                ],
                "runs_without_model_version": u.runs_without_model,
                "latest_run": {
                    "run_id": u.latest.run_id,
                    "when": _when(u.latest.when),
                    "model_version": u.latest.model_version,
                    "inputs": list(u.latest.inputs),
                },
                "run_records": {
                    "runs": u.activity.runs,
                    "first_seen": _when(u.activity.first_seen),
                    "last_seen": _when(u.activity.last_seen),
                    "span_days": u.span_days,
                    # A span, never a retention policy: the events carry none.
                    "retention_policy": None,
                },
            }
            for u in record.use_cases
        ],
        "declared": [
            {
                "name": d.name,
                "domain": d.domain,
                "evidence": "declared",
                "purpose": sourced(d.purpose),
                "legal_basis": sourced(d.legal_basis),
                "model": d.model,
                "inputs": list(d.inputs),
                "note": d.note,
                "run_records": None,
            }
            for d in record.declared
        ],
        "scope": {
            "source": record.scope.source,
            "window": {"since": _when(record.scope.since), "until": _when(record.scope.until)},
            "windowed": record.scope.windowed,
            "events": record.scope.events,
            "activities": record.scope.activities,
            "use_cases": record.scope.use_cases,
            "declared": record.scope.declared,
            "runs": record.scope.runs,
            "out_of_view": record.scope.OUT_OF_VIEW,
        },
        "complete": record.complete,
        "reasons": list(record.completeness.reasons),
    }
    return _json.dumps(payload, indent=indent, ensure_ascii=False) + "\n"


@xlsx.register
def _(record: deployer_module.DeployerRecord) -> bytes:
    from .xlsx import deployer_workbook

    return deployer_workbook(record)


#: Public name to renderer. The CLI's `--format` choices come from this, so a
#: new format is added in one place.
FORMATS: dict[str, object] = {
    "text": text,
    "markdown": markdown,
    "json": json,
    "xlsx": xlsx,
}

#: Formats that return bytes. A caller has to know before it decides whether
#: standard output is somewhere this can go — see `is_binary`.
BINARY = frozenset({"xlsx"})

#: File suffix to format, for inferring from `--out`. Someone writing
#: `--out ropa.md` means markdown, and silently filling that file with terminal
#: text would be a small lie in the one artefact that must not contain any.
BY_SUFFIX = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
    ".txt": "text",
    ".xlsx": "xlsx",
}


def names() -> Iterable[str]:
    return FORMATS.keys()


def is_binary(fmt: str) -> bool:
    """Whether this format produces bytes rather than text."""
    return fmt in BINARY


def infer(out: str | None, *, default: str = "text") -> str:
    """The format implied by an output filename, or *default*.

    Only consulted when `--format` was not given, so an explicit flag always
    wins over a guess made from a file extension.
    """
    if not out:
        return default
    suffix = out[out.rfind(".") :].lower() if "." in out else ""
    return BY_SUFFIX.get(suffix, default)
