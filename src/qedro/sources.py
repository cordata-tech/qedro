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
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from . import words
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
    #: Rendered as `could not read {entry}`, so each entry names a thing
    #: and puts its reason in parentheses — `events.ndjson (JSONDecodeError)`.
    #: Two of these were sentences and read as `could not read /x does not
    #: exist`.
    unreadable: tuple[str, ...] = ()
    truncated: bool = False
    #: Files in the directory that were not read because nothing about them
    #: says they hold events, as paths relative to the directory. Counted so
    #: the summary can say so, and kept out of `clean`: a README or a
    #: compressed archive beside the events is what a directory looks like,
    #: and withholding the mark for it would teach people to ignore the reason.
    #: See cordata-tech/qedro#28.
    passed_over: tuple[str, ...] = ()

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


def passed_over_text(paths: tuple[str, ...]) -> str:
    """Files a directory read passed over, as one phrase, or "" when none were.

    One copy for the `qedro events` summary and every projection's scope
    statement, which say the same thing about the same read.
    """
    if not paths:
        return ""
    n = len(paths)
    shown = ", ".join(paths[:3])
    more = f" and {n - 3} more" if n > 3 else ""
    neither = words.plural(
        n,
        "its name nor its start says it holds",
        "their names nor their starts say they hold",
    )
    return f"{words.count(n, 'file')} not read, because neither {neither} events: {shown}{more}"


def utc(value: datetime) -> datetime:
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
    when = utc(when)
    if since is not None and when < utc(since):
        return False
    return until is None or when <= utc(until)


# --------------------------------------------------------------------------
# A directory of JSON
# --------------------------------------------------------------------------


def _records(text: str, suffix: str) -> Iterator[Any]:
    """Yield JSON records from one file's text, whatever shape it is in.

    Three shapes turn up in practice and none is worth making the user
    identify: newline-delimited events, a single event, and an array of them.
    Sniffing is cheaper than a flag, and a flag would be got wrong. Takes the
    text rather than a path, so a file on disk and an object in a bucket are
    parsed by the same code.
    """
    stripped = text.lstrip()
    if not stripped:
        return

    if stripped[0] == "[":
        parsed = json.loads(text)
        if isinstance(parsed, list):
            yield from parsed
        return

    if suffix in (".ndjson", ".jsonl") or "\n" in stripped.strip():
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


#: How much of a file with no extension is read to decide whether it holds events.
HEAD = 512


def _holds_events(suffix: str, head: Callable[[], bytes]) -> bool:
    """Whether a file is one to read, from its name or, failing that, its start.

    A recognised suffix decides it. A file with no suffix at all is read when
    its first non-blank byte opens JSON, because that is what an appending
    OpenLineage file transport writes: the Python client's to exactly the path
    configured and the Java client's to its `location`, neither adding an
    extension. Anything else — `.md`, `.gz`, `.log` — is passed over and
    counted, since sniffing a README that opens with `[` would read it as a
    broken array and withhold the mark over a file nobody meant as events.

    `head` returns the first :data:`HEAD` bytes and is called only when the
    name does not decide it, so neither a directory nor a bucket opens every
    file to choose. Shared by both readers: one rule, so the same files give
    the same answer wherever they are kept.
    """
    if suffix in SUFFIXES:
        return True
    if suffix:
        return False
    try:
        start = head().lstrip()
    except OSError:
        return False
    return start[:1] in (b"{", b"[")


def _hidden(relative: PurePosixPath) -> bool:
    """A dotfile, or anything inside a dot-directory such as `.git`.

    Neither sniffed nor counted as passed over, which would otherwise be
    thousands of `.git` objects or one `.DS_Store` reported on every run.
    """
    return any(part.startswith(".") for part in relative.parts)


def _select(relative: PurePosixPath, head: Callable[[], bytes]) -> bool | None:
    """Read it (True), name it as passed over (False), or leave it out (None).

    A recognised suffix is read wherever it sits, as it always was. Hidden
    paths are otherwise skipped before sniffing, so a `.git` directory costs a
    walk and not an open per object.
    """
    if relative.suffix not in SUFFIXES and _hidden(relative):
        return None
    return _holds_events(relative.suffix, head)


def _take(name: str, suffix: str, text: str, report: ReadReport, events: list[Event]) -> None:
    """Parse one file's text into *events*, counting into *report* what it cannot use."""
    report.files += 1
    try:
        records = list(_records(text, suffix))
    except json.JSONDecodeError as exc:
        report.unreadable += (f"{name} ({type(exc).__name__})",)
        return
    for record in records:
        event = parse_event(record) if record is not None else None
        if event is None:
            report.skipped_records += 1
            continue
        events.append(event)


def _head(path: Path) -> bytes:
    with path.open("rb") as handle:
        return handle.read(HEAD)


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
        return events, ReadReport(origin=str(root), unreadable=(f"{root} (does not exist)",))

    if root.is_file():
        # Pointing at the file is what anyone does first, and `rglob` on a file
        # yields nothing — so this used to report a clean zero and exit 0, with
        # a reason that blamed the estate for what was really a path the reader
        # would not read. Found by running it against a real dbt export.
        if not _holds_events(root.suffix, lambda: _head(root)):
            return events, ReadReport(
                origin=str(root),
                unreadable=(
                    (
                        f"{root} (not one of {', '.join(SUFFIXES)}, "
                        "nor a file with no extension that starts with JSON)"
                    ),
                ),
            )
        files = [root]
    else:
        files, passed_over = [], []
        for p in sorted(root.rglob("*") if recursive else root.glob("*")):
            if not p.is_file():
                continue
            relative = PurePosixPath(p.relative_to(root).as_posix())
            chosen = _select(relative, lambda p=p: _head(p))
            if chosen:
                files.append(p)
            elif chosen is False:
                passed_over.append(relative.as_posix())
        report.passed_over = tuple(passed_over)

    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            report.files += 1
            report.unreadable += (f"{f.name} ({type(exc).__name__})",)
            continue
        _take(f.name, f.suffix, text, report, events)

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
        query["after"] = utc(since).isoformat()
    if until is not None:
        query["before"] = utc(until).isoformat()

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
# An object-store prefix
# --------------------------------------------------------------------------

#: The address schemes read as a bucket, and the extra that installs each one's
#: backend. Where a composite OpenLineage transport puts the raw copy for every
#: catalog that cannot give events back, and the reason this reader exists —
#: see cordata-tech/qedro#30 and `docs/pilot.md`.
BUCKETS = {
    "s3": "s3",
    "gs": "gcs",
    "gcs": "gcs",
    "az": "azure",
    "abfs": "azure",
    "abfss": "azure",
}


class _ReadOnly:
    """The three calls this module makes on a filesystem, and no others.

    fsspec filesystems can write, delete and move. This wrapper is the only
    thing the bucket reader holds, so no code here can reach those methods —
    the same property the HTTP source has by being unable to build anything but
    a GET, and asserted the same way, by a test that hands it a filesystem
    failing on any other call. The credentials the backend found in the
    environment may well allow writing; nothing here can use them to.
    """

    def __init__(self, filesystem: Any) -> None:
        self._fs = filesystem

    def list(self, prefix: str) -> list[str]:
        return sorted(self._fs.find(prefix))

    def head(self, key: str) -> bytes:
        return self._fs.cat_file(key, start=0, end=HEAD)

    def read(self, keys: list[str]) -> dict[str, Any]:
        """Every object at once, so an async backend fetches them concurrently.

        The Java client's S3 and GCS transports write one object per event, so a
        pilot's window can be thousands of small objects, and one request at a
        time would make the first run the slow one. A failure comes back as the
        exception in place of the bytes rather than stopping the others.
        """
        return self._fs.cat(keys, on_error="return") if keys else {}


def _filesystem(address: str) -> tuple[Any, str]:
    """The backend for *address*, or a sentence saying which extra installs it."""
    scheme = address.split("://", 1)[0].lower()
    missing = ConfigError(
        f"reading {scheme}:// needs an optional dependency — "
        f"pip install 'qedro[{BUCKETS.get(scheme, scheme)}]'"
    )
    # Either import can be the missing one: fsspec itself, or the backend it
    # loads for this scheme, which fsspec reports as an ImportError of its own.
    try:
        from fsspec.core import url_to_fs

        return url_to_fs(address)
    except ImportError:
        raise missing from None


def read_bucket(address: str, *, filesystem: Any = None) -> tuple[list[Event], ReadReport]:
    """Read every event under an `s3://`, `gs://` or `az://` prefix.

    The same selection and the same parsing as :func:`read_dir`, so a prefix
    copied to disk and the same prefix read in place give the same events and
    the same report; `tests/test_sources.py` reads one set of files both ways
    to hold that. Credentials come from the environment through the backend's
    own chain — an AWS profile or role, Google's application default
    credentials, Azure's — and never from a flag.

    *filesystem* is for tests, which use fsspec's in-memory one rather than a
    cloud; the address's path is then read from it as given.
    """
    report = ReadReport(origin=address)
    events: list[Event] = []

    try:
        if filesystem is None:
            filesystem, prefix = _filesystem(address)
        else:
            prefix = address.split("://", 1)[-1].rstrip("/")
        store = _ReadOnly(filesystem)
        keys = store.list(prefix)
    except ConfigError:
        raise
    except Exception as exc:  # noqa: BLE001 — every backend raises its own types
        # The edge of the network, where each backend raises its own types — a
        # missing bucket, a role that cannot list, no credentials at all. All of
        # them are a read that did not happen, which the report carries and the
        # mark is withheld for, exactly as for an unreachable Marquez.
        report.unreadable += (f"{address} ({type(exc).__name__})",)
        return events, report

    if not keys:
        # Unlike an empty directory, an empty prefix does not exist in an object
        # store, so this is almost always a mistyped address. Reporting it as a
        # clean read of nothing would blame the lineage for a typo.
        report.unreadable += (f"{address} (no objects under this prefix)",)
        return events, report

    chosen, passed_over = [], []
    for key in keys:
        # A single object addressed directly lists as itself, and is named by
        # its own name rather than by an empty path relative to itself.
        # Backends differ on a leading slash — the in-memory one adds it, s3fs
        # does not — so both sides are compared without one.
        if key.strip("/") == prefix.strip("/"):
            relative = PurePosixPath(PurePosixPath(key).name)
        else:
            relative = PurePosixPath(key.lstrip("/")).relative_to(prefix.strip("/"))
        selected = _select(relative, lambda key=key: store.head(key))
        if selected:
            chosen.append((key, relative))
        elif selected is False:
            passed_over.append(relative.as_posix())
    report.passed_over = tuple(passed_over)

    fetched = store.read([key for key, _ in chosen])
    for key, relative in chosen:
        body = fetched.get(key, FileNotFoundError(key))
        if not isinstance(body, bytes):
            # An exception in place of the bytes: one object that failed, of
            # whatever type the backend raises, and the others still read.
            report.files += 1
            report.unreadable += (f"{relative.name} ({type(body).__name__})",)
            continue
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            report.files += 1
            report.unreadable += (f"{relative.name} ({type(exc).__name__})",)
            continue
        _take(relative.name, relative.suffix, text, report, events)

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

    A scheme in :data:`BUCKETS` is read as an object-store prefix. Anything
    else carrying a ``scheme://`` is refused rather than tried as a path: nobody
    means a directory by ``ftp://host``, and *"ftp:/host does not exist"* sends
    them looking for a typo instead of at the sentence that says which
    addresses this reads.
    """
    scheme = source.split("://", 1)[0].lower() if _SCHEME.match(source) else ""
    if scheme in BUCKETS:
        events, report = read_bucket(source)
        if since is None and until is None:
            return events, report
        events = [e for e in events if in_window(e, since, until)]
        report.events = len(events)
        return events, report

    if scheme and scheme not in ("http", "https"):
        schemes = ", ".join(f"{s}://" for s in BUCKETS)
        raise ConfigError(
            f"{source!r}: only a directory, an http:// address, or a bucket ({schemes}) can be read"
        )

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
