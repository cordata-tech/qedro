"""Turning a :class:`~qedro.ropa.Record` into something a person receives.

Four formats — text for a terminal, markdown for a repository or a document,
json for whatever consumes this next, and xlsx for the auditor, who asks for a
spreadsheet and will not be talked out of it. The first three are strings; xlsx
is bytes and lives in its own module, because a workbook is layout as well as
content and mixing that in here would bury the two rules below.

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

from . import TOMBSTONE
from .ropa import Activity, Record, Scope

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


def text(record: Record, *, symbol: bool = True, width: int = 88) -> str:
    """The terminal rendering. Dense, and readable without scrolling."""
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

    if record.complete:
        mark = TOMBSTONE if symbol else "[complete]"
        out.append(f"  every activity stands on emitted evidence   {mark}")
    else:
        out.append("  this record does not claim to be a proof:")
        out.extend(f"    ! {reason}" for reason in record.completeness.reasons)

    return "\n".join(out) + "\n"


def _scope_text(scope: Scope, *, width: int) -> list[str]:
    out = ["  Scope of this record", f"    source        {scope.source or 'unknown'}"]
    out.append(f"    window        {scope.window()}")
    out.append(
        f"    in view       {scope.jobs} jobs, {scope.datasets} datasets, {scope.events} events"
    )
    if scope.namespaces:
        out.append(f"    namespaces    {', '.join(scope.namespaces)}")
    out.append(
        f"    provenance    {scope.evidenced} evidenced, {scope.from_mapping} from the "
        f"mapping file, {scope.undeclared} undeclared"
    )
    if scope.domains_silent:
        out.append(f"    silent        {', '.join(scope.domains_silent)} (in scope, no lineage)")
    for line in _wrap(scope.OUT_OF_VIEW, width - 4):
        out.append(f"    {line}")
    return out


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


def markdown(record: Record) -> str:
    """For a repository, a wiki, or a document somebody prints."""
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

    out += ["", "## Scope of this record", ""]
    out += [
        f"- **Source** — {record.scope.source or 'unknown'}",
        f"- **Window** — {record.scope.window()}",
        (
            f"- **In view** — {record.scope.jobs} jobs, "
            f"{record.scope.datasets} datasets, {record.scope.events} events"
        ),
        (
            f"- **Provenance** — {record.scope.evidenced} evidenced, "
            f"{record.scope.from_mapping} from the mapping file, "
            f"{record.scope.undeclared} undeclared"
        ),
    ]
    if record.scope.domains_silent:
        out.append(f"- **Declared in scope but silent** — {', '.join(record.scope.domains_silent)}")
    out += ["", record.scope.OUT_OF_VIEW, ""]

    if record.complete:
        out += [f"Every activity in this record stands on emitted evidence. {TOMBSTONE}", ""]
    else:
        out += ["**This record does not claim to be a proof.**", ""]
        out += [f"- {reason}" for reason in record.completeness.reasons]
        out.append("")

    return "\n".join(out)


def _provenance_cell(activity: Activity) -> str:
    sources = {str(activity.purpose.provenance), str(activity.legal_basis.provenance)}
    if sources == {"facet"}:
        return "emitted facet"
    if "mapping" in sources:
        return "mapping file"
    return "not declared"


def json(record: Record, *, indent: int = 2) -> str:
    """For whatever consumes this next.

    Provenance is a field per value rather than a summary, so a consumer can
    make the evidenced/asserted distinction without re-deriving it.
    """
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


def xlsx(record: Record) -> bytes:
    """The workbook, as bytes.

    openpyxl is imported here rather than at module scope so that `qedro
    events`, and every text rendering, pays nothing for a format they do not
    produce.
    """
    from .xlsx import workbook

    return workbook(record)


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
