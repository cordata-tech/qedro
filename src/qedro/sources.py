"""Where events come from.

One source so far: a directory on disk. That is deliberately the first one
rather than an API client, because it is the lowest bar to trying this thing.
Anyone can point a lineage backend at a folder, or export from one, and a
reader that needs a running Marquez before it can do anything has a much
smaller set of people who will ever run it.

A Marquez-compatible HTTP source comes next and produces the same
:class:`~qedro.events.Event` objects, so nothing downstream changes.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .events import Event, parse_event

#: Read both. `.ndjson` and `.jsonl` name the same format, and which one an
#: emitter picks is a coin flip.
SUFFIXES = (".json", ".ndjson", ".jsonl")


@dataclass
class ReadReport:
    """What the read found, including what it could not use.

    Counted rather than logged and forgotten. A projection built on 900 of
    1,000 events is not wrong, but it is not complete either, and the summary
    has to be able to say so — see :mod:`qedro.mark`.
    """

    files: int = 0
    events: int = 0
    skipped_records: int = 0
    unreadable_files: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return self.skipped_records == 0 and not self.unreadable_files

    def reasons(self) -> list[str]:
        """Phrasings fit for a CLI summary line, empty when the read was clean."""
        out = []
        if self.skipped_records:
            out.append(f"{self.skipped_records} records were not usable OpenLineage events")
        if self.unreadable_files:
            shown = ", ".join(self.unreadable_files[:3])
            more = (
                f" and {len(self.unreadable_files) - 3} more"
                if len(self.unreadable_files) > 3
                else ""
            )
            out.append(f"could not read {shown}{more}")
        return out


def _records(path: Path) -> Iterator[Any]:
    """Yield JSON records from one file, whatever shape it is in.

    Three shapes turn up in practice and none is worth making the user
    identify: newline-delimited events, a single event, and an array of them.
    Sniffing is cheaper than a flag, and a flag would be got wrong.
    """
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if not stripped:
        return

    if stripped[0] == "[":
        parsed = json.loads(text)
        if isinstance(parsed, list):
            yield from parsed
        return

    if path.suffix in (".ndjson", ".jsonl") or "\n" in stripped.strip():
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield None  # counted as skipped by the caller
        return

    yield json.loads(text)


def read_dir(path: str | Path, *, recursive: bool = True) -> tuple[list[Event], ReadReport]:
    """Read every event under ``path``.

    Returns the events *and* a report, rather than logging problems and
    returning only what worked. The caller needs both: the events to project
    from, and the report to decide whether the result may claim to be
    complete.
    """
    root = Path(path)
    report = ReadReport()
    events: list[Event] = []

    if not root.exists():
        return events, ReadReport(unreadable_files=(f"{root} does not exist",))

    files = sorted(
        p
        for p in (root.rglob("*") if recursive else root.glob("*"))
        if p.is_file() and p.suffix in SUFFIXES
    )

    for f in files:
        report.files += 1
        try:
            records = list(_records(f))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            report.unreadable_files += (f"{f.name} ({type(exc).__name__})",)
            continue
        for record in records:
            event = parse_event(record) if record is not None else None
            if event is None:
                report.skipped_records += 1
                continue
            events.append(event)

    report.events = len(events)
    return events, report
