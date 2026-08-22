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
from . import provenance as provenance_module
from . import quality as quality_module
from .ropa import Activity, Record
from .scope import Scope

#: What each provenance looks like in a rendered table. The evidenced case gets
#: no decoration: it is the normal case, and marking it would make the record
#: look like it was arguing with itself.
BADGE = {
    "facet": "",
    "mapping": " (mapping)",
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
    controller = record.controller.name or "— no controller declared"
    out.append(f"Record of processing activities — {controller}")
    if record.controller.contact:
        out.append(f"  contact: {record.controller.contact}")
    out.append("")

    for activity in record.activities:
        out.append(f"  {activity.key}")
        out.append(f"    purpose       {_field(activity.purpose)}")
        out.append(f"    legal basis   {_field(activity.legal_basis)}")
        if activity.inputs:
            out.append(f"    reads         {', '.join(activity.inputs)}")
        if activity.outputs:
            out.append(f"    writes        {', '.join(activity.outputs)}")
        out.append(f"    runs          {activity.runs} in window, last {_when(activity.last_seen)}")
        out.append("")

    out.extend(_scope_text(record.scope, width=width))
    out.append("")
    out.extend(_verdict_text(record, "every activity stands on emitted evidence", symbol=symbol))

    return "\n".join(out) + "\n"


def _scope_text(scope: Scope, *, width: int, title: str = "Scope of this record") -> list[str]:
    """Shared by every projection. The labels come from the scope itself."""
    out = [f"  {title}", f"    source        {scope.source or 'unknown'}"]
    out.append(f"    window        {scope.window()}")
    out.extend(f"    {label:<13} {value}" for label, value in scope.lines())
    if scope.domains_silent:
        out.append(f"    silent        {', '.join(scope.domains_silent)} (in scope, no lineage)")
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
    words, lines, current = paragraph.split(), [], ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


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
        "| Activity | Purpose | Legal basis | Source | Reads | Writes | Runs |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in record.activities:
        out.append(
            f"| `{a.key}` | {a.purpose.value or '—'} | {a.legal_basis.value or '—'} "
            f"| {_provenance_cell(a)} | {len(a.inputs)} | {len(a.outputs)} | {a.runs} |"
        )

    out += _scope_markdown(record.scope)
    out += _verdict_markdown(record, "Every activity in this record stands on emitted evidence.")

    return "\n".join(out)


def _scope_markdown(scope: Scope) -> list[str]:
    out = ["", "## Scope of this record", ""]
    out += [
        f"- **Source** — {scope.source or 'unknown'}",
        f"- **Window** — {scope.window()}",
    ]
    out += [f"- **{label[0].upper()}{label[1:]}** — {value}" for label, value in scope.lines()]
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
        "scope": {
            "source": record.scope.source,
            "window": {
                "since": _when(record.scope.since),
                "until": _when(record.scope.until),
            },
            "events": record.scope.events,
            "jobs": record.scope.jobs,
            "datasets": record.scope.datasets,
            "namespaces": list(record.scope.namespaces),
            "domains_declared": list(record.scope.domains_declared),
            "domains_seen": list(record.scope.domains_seen),
            "domains_silent": list(record.scope.domains_silent),
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


def _activity_json(activity: Activity) -> dict[str, object]:
    return {
        "job": activity.key,
        "namespace": activity.namespace,
        "name": activity.name,
        "domain": activity.domain,
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
    controller = record.controller.name or "— no controller declared"
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
            "domains_declared": list(record.scope.domains_declared),
            "domains_seen": list(record.scope.domains_seen),
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
