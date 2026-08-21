"""Where events come from.

Two sources, and the order they arrived in was deliberate. A **directory on
disk** came first because it is the lowest bar to trying this thing: anyone can
export from a lineage backend into a folder, and a reader that needs a running
Marquez before it can do anything has a much smaller set of people who will ever
run it. A **Marquez-compatible HTTP API** came second because that is where the
events already are once somebody is past trying.

Both produce the same :class:`~qedro.events.Event` objects and the same
:class:`ReadReport`, so nothing downstream knows or cares which was used. That
is the property worth protecting: a projection that behaves differently against
a directory than against an API is a projection with two implementations.

The HTTP source is **read-only by construction**, not by policy. The only verb
this module can issue is GET — there is no code path here that builds any other
request, and nothing in the process holds a credential that could acquire a
write scope. See :func:`_get`.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .events import Event, parse_event

#: Read both. `.ndjson` and `.jsonl` name the same format, and which one an
#: emitter picks is a coin flip.
SUFFIXES = (".json", ".ndjson", ".jsonl")

#: Marquez's raw-event endpoint. It returns OpenLineage RunEvents as emitted,
#: rather than Marquez's own job and dataset projection of them, which is why
#: this is the endpoint to read: `parse_event` needs no special case for it.
LINEAGE_PATH = "/api/v1/events/lineage"

#: How many events one request asks for. Some deployments cap `limit`
#: server-side, so the pager trusts what came back rather than what it asked
#: for.
PAGE_SIZE = 100

#: Stop here rather than paging through a decade of history when no window was
#: given. Counted on events *fetched*, not events kept, so the bound holds even
#: when a backend ignores the window parameters and most of what arrives is
#: discarded. Hitting it is a reported condition, never a silent truncation: a
#: projection built on the first 10,000 of 400,000 events is not complete and
#: must not be able to claim that it is.
MAX_EVENTS = 10_000

TIMEOUT = 30.0

#: What a URL looks like before it is a URL. Used only to tell a mistyped
#: address apart from a directory — `//` is required, so a directory named
#: `s3:` is still a directory.
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")


@dataclass
class ReadReport:
    """What the read found, including what it could not use.

    Counted rather than logged and forgotten. A projection built on 900 of
    1,000 events is not wrong, but it is not complete either, and the summary
    has to be able to say so — see :mod:`qedro.mark`.

    ``files`` and ``pages`` are the same fact in the two source shapes, and
    exactly one of them is ever non-zero. They are kept apart rather than
    merged into a units counter because the summary line has to name the noun,
    and *"14 files"* against a URL reads as a bug in the tool.
    """

    origin: str = ""
    files: int = 0
    pages: int = 0
    events: int = 0
    skipped_records: int = 0
    unreadable: tuple[str, ...] = ()
    truncated: bool = False

    @property
    def clean(self) -> bool:
        return not self.skipped_records and not self.unreadable and not self.truncated

    def reasons(self) -> list[str]:
        """Phrasings fit for a CLI summary line, empty when the read was clean."""
        out = []
        if self.skipped_records:
            out.append(f"{self.skipped_records} records were not usable OpenLineage events")
        if self.unreadable:
            shown = ", ".join(self.unreadable[:3])
            more = f" and {len(self.unreadable) - 3} more" if len(self.unreadable) > 3 else ""
            out.append(f"could not read {shown}{more}")
        if self.truncated:
            out.append(
                f"stopped after {MAX_EVENTS} events and the backend holds more, "
                "so the window is not fully covered"
            )
        return out


def _utc(value: datetime) -> datetime:
    """Naive timestamps are read as UTC.

    Emitters disagree about the suffix, and refusing to compare is worse than
    making the one assumption every lineage backend already makes.
    """
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def in_window(event: Event, since: datetime | None, until: datetime | None) -> bool:
    """Whether an event falls inside the requested window.

    An event whose ``eventTime`` did not parse has no place in a window and is
    dropped when one is asked for — but kept when none is, because then there
    is nothing to place it against.
    """
    if since is None and until is None:
        return True
    when = event.event_time
    if when is None:
        return False
    when = _utc(when)
    if since is not None and when < _utc(since):
        return False
    return until is None or when <= _utc(until)


# --------------------------------------------------------------------------
# A directory of JSON
# --------------------------------------------------------------------------


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
    report = ReadReport(origin=str(root))
    events: list[Event] = []

    if not root.exists():
        return events, ReadReport(origin=str(root), unreadable=(f"{root} does not exist",))

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
            report.unreadable += (f"{f.name} ({type(exc).__name__})",)
            continue
        for record in records:
            event = parse_event(record) if record is not None else None
            if event is None:
                report.skipped_records += 1
                continue
            events.append(event)

    report.events = len(events)
    return events, report


# --------------------------------------------------------------------------
# A Marquez-compatible HTTP API
# --------------------------------------------------------------------------


def lineage_url(
    base: str,
    *,
    limit: int,
    offset: int,
    since: datetime | None = None,
    until: datetime | None = None,
) -> str:
    """Build one page request.

    ``base`` is forgiving on purpose — people paste whatever their browser had.
    A bare host, a host with ``/api/v1``, or the full endpoint all resolve to
    the same URL, because getting that wrong produces a 404 the user has to
    guess at rather than a message they can act on.
    """
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in ("http", "https"):
        # `file://` through urlopen would read local paths, and no other scheme
        # is a lineage backend. Refuse rather than reinterpret.
        raise ConfigError(f"{base!r}: only http:// and https:// addresses can be read")
    if not parsed.netloc:
        raise ConfigError(f"{base!r}: no host in the address")

    path = parsed.path.rstrip("/")
    if not path.endswith(LINEAGE_PATH):
        path = path.removesuffix("/api/v1") + LINEAGE_PATH

    query = {"limit": str(limit), "offset": str(offset), "sortDirection": "asc"}
    # Marquez names these `after` and `before`. They are an optimisation, never
    # the guarantee: the window is applied again to what comes back, so a
    # backend that ignores them, or spells them differently, still yields a
    # correct result rather than a silently wider one.
    if since is not None:
        query["after"] = _utc(since).isoformat()
    if until is not None:
        query["before"] = _utc(until).isoformat()

    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, urllib.parse.urlencode(query), "")
    )


def _get(url: str, *, timeout: float) -> Any:
    """Fetch and decode one page.

    The single place this module touches the network, and it issues GET. There
    is no branch here that takes a method, a body or a verb from a caller, so
    *read-only* is a property of the code rather than a rule somebody has to
    keep following.

    A token, when there is one, comes from the environment and never from argv:
    a secret on a command line lands in shell history and in `ps`. It is a read
    credential for a lineage backend, and nothing here can use it to write,
    because nothing here can write.
    """
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "application/json")
    token = os.environ.get("QEDRO_API_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _page(payload: Any) -> list[Any] | None:
    """The events out of one response body, or None if it is not a page at all.

    Marquez returns ``{"events": [...], "totalCount": n}``; other services
    speaking the same endpoint return a bare array. Both are cheap to accept. A
    body that is neither is a fact to report rather than one to guess at.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        events = payload.get("events")
        if isinstance(events, list):
            return events
    return None


def read_api(
    base: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    page_size: int = PAGE_SIZE,
    max_events: int = MAX_EVENTS,
    timeout: float = TIMEOUT,
) -> tuple[list[Event], ReadReport]:
    """Read events from a Marquez-compatible lineage API.

    Pages until the backend runs out or ``max_events`` have been fetched. In
    the second case it asks for one more event before reporting truncation,
    because a budget that happens to equal the size of the history is not a
    hole and should not cost the artefact its mark.

    A transport failure is recorded and ends the read rather than propagating.
    Half a window is still worth projecting from, as long as the artefact says
    that is what it is — which is the whole argument of :mod:`qedro.mark`.
    """
    report = ReadReport(origin=base)
    events: list[Event] = []
    offset = 0
    exhausted_budget = False

    def fetch(limit: int, at: int) -> list[Any] | None:
        """One page, or None with the reason already recorded on the report."""
        url = lineage_url(base, limit=limit, offset=at, since=since, until=until)
        try:
            payload = _get(url, timeout=timeout)
        except urllib.error.HTTPError as exc:
            report.unreadable += (f"{base} (HTTP {exc.code})",)
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            report.unreadable += (f"{base} ({type(exc).__name__})",)
            return None
        except (json.JSONDecodeError, UnicodeDecodeError):
            report.unreadable += (f"{base} (response was not JSON)",)
            return None

        page = _page(payload)
        if page is None:
            report.unreadable += (f"{base} (no events in the response body)",)
        return page

    while True:
        if offset >= max_events:
            exhausted_budget = True
            break

        page = fetch(min(page_size, max_events - offset), offset)
        if page is not None:
            report.pages += 1
        if not page:
            break

        for record in page:
            event = parse_event(record)
            if event is None:
                report.skipped_records += 1
                continue
            if in_window(event, since, until):
                events.append(event)

        # Trust the page rather than the request: a backend that caps `limit`
        # below what was asked would otherwise look like the end of the data.
        offset += len(page)
        if len(page) < page_size:
            break

    if exhausted_budget:
        # Truncation is only a claim once there is evidence for it. A failed
        # probe leaves it True: not being able to show the history ended is not
        # the same as showing that it did, and the artefact must not round the
        # difference in its own favour.
        probe = fetch(1, offset)
        report.truncated = probe is None or bool(probe)

    report.events = len(events)
    return events, report


# --------------------------------------------------------------------------
# One entry point
# --------------------------------------------------------------------------


def read(
    source: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    recursive: bool = True,
    page_size: int = PAGE_SIZE,
    max_events: int = MAX_EVENTS,
    timeout: float = TIMEOUT,
) -> tuple[list[Event], ReadReport]:
    """Read from whichever source ``source`` names.

    Everything above this line wants events and does not care where they came
    from. An ``http://`` or ``https://`` prefix is the only signal used — a
    path can contain a colon, and sniffing anything looser would eventually
    read a directory as a URL.

    Anything else carrying a ``scheme://`` is refused rather than tried as a
    path. Nobody means a directory by ``s3://bucket``, and *"s3:/bucket does not
    exist"* sends them looking for a typo instead of at the sentence that says
    which addresses this reads.
    """
    if _SCHEME.match(source) and not source.startswith(("http://", "https://")):
        raise ConfigError(f"{source!r}: only a directory or an http:// address can be read")

    if source.startswith(("http://", "https://")):
        return read_api(
            source,
            since=since,
            until=until,
            page_size=page_size,
            max_events=max_events,
            timeout=timeout,
        )

    events, report = read_dir(source, recursive=recursive)
    if since is None and until is None:
        return events, report
    events = [e for e in events if in_window(e, since, until)]
    report.events = len(events)
    return events, report
