"""CLI entry point.

One command so far. ``qedro events`` reads a directory or a Marquez-compatible
API and says what it found — not a projection, and it does not pretend to be
one, but it is the thing to run first to find out whether your lineage is
readable at all.

The projections come next. This exists so the reader is usable before they
land, and so the completeness rule is exercised end to end rather than only
in tests.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import (
    __version__,
    attribution,
    compare,
    declared,
    demo,
    deployer,
    erasure,
    provenance,
    quality,
    render,
    ropa,
    signoff,
    staleness,
    vocabulary,
    words,
)
from . import config as config_module
from . import references as references_module
from .errors import ConfigError, QedroError, UsageError
from .mark import Completeness
from .sources import passed_over_text, read

#: What every command that reads events accepts, said once.
SOURCE_HELP = (
    "a directory of OpenLineage events (.json, .ndjson, .jsonl), an s3://, gs:// or az:// "
    "prefix holding them, or the base URL of a Marquez-compatible API"
)


def _instant(value: str) -> datetime:
    """A `--since` / `--until` argument.

    A bare date is the start of that day. `--since 2026-01-01` meaning
    *"anything on or after the first"* is what everyone expects it to mean, and
    `fromisoformat` already reads both spellings on the 3.12 floor.
    """
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not an ISO-8601 date or timestamp (try 2026-01-01)"
        ) from None


def _window(args: argparse.Namespace) -> tuple[datetime | None, datetime | None]:
    """`--days 90`, resolved against `--until` or against now.

    Sugar over `--since`, because *the last quarter* is how anybody asks for an
    assertion history and computing the date by hand is a papercut. An explicit
    `--since` wins: two flags meaning the same thing must not silently
    disagree, and the one the user typed is the one they meant.
    """
    since, until = args.since, args.until
    if args.days is not None and since is None:
        end = until or datetime.now(UTC)
        since = end - timedelta(days=args.days)
    return since, until


def _events(target: str, *, symbol: bool, since: datetime | None, until: datetime | None) -> int:
    events, report = read(target, since=since, until=until)

    completeness = Completeness()
    for reason in report.reasons():
        completeness = completeness.degraded(reason)

    if not events and report.clean:
        # A clean read of nothing is not a proof of anything. The mark says
        # *this stands on its own evidence*, and there is no evidence here —
        # which is the difference between "nothing happened" and "nothing was
        # recorded" that a reviewer needs flagged.
        completeness = completeness.degraded(
            "no events in the window — nothing was recorded, "
            "which is not the same as nothing having happened"
        )

    if not events and not report.clean:
        # Nothing read and something wrong: a failure, not a quiet success
        # with an empty result.
        for reason in report.reasons():
            print(f"  {reason}", file=sys.stderr)
        if passed := passed_over_text(report.passed_over):
            print(f"  {passed}", file=sys.stderr)
        return 1

    by_type = Counter(e.event_type for e in events)
    jobs = {e.job.key for e in events}
    datasets = {d.key for e in events for d in e.datasets}

    # A directory has files and an API has pages, and naming the wrong one
    # reads as a bug in the tool. Decided by the source rather than by which
    # count is non-zero, which said `0 pages` of a directory it read nothing in.
    fetched = (
        words.count(report.pages, "page")
        if report.origin.startswith(("http://", "https://"))
        else words.count(report.partitions, "partition")
        if report.origin.startswith("kafka://")
        else words.count(report.files, "file")
    )
    summary = " · ".join(
        [
            words.count(report.events, "event"),
            words.count(len(jobs), "job"),
            words.count(len(datasets), "dataset"),
            fetched,
        ]
    )
    suffix = completeness.suffix(symbol=symbol)
    print(f"  {summary}{'  ' + suffix if suffix else ''}")

    if by_type:
        print("  " + ", ".join(f"{t.lower()} {n}" for t, n in sorted(by_type.items())))
    # Not a reason: the mark stands. But a directory read as smaller than it is
    # has to say so, or the summary describes the files it read as if they
    # were everything it was pointed at (#28).
    if passed := passed_over_text(report.passed_over):
        print(f"  {passed}")
    # Not a reason either: each event is counted once, and the source held copies (#58).
    if report.duplicates:
        copies = words.count(report.duplicates, "record")
        print(f"  {copies} identical to one already read, counted once")

    # Reasons are printed, not only counted. A reader who cannot see why the
    # mark is missing has been told nothing useful.
    for reason in completeness.reasons:
        print(f"  ! {reason}", file=sys.stderr)

    return 0


def _ropa(
    source: str,
    *,
    symbol: bool,
    since: datetime | None,
    until: datetime | None,
    config_path: str | None,
    vocabulary_path: str | None,
    fmt: str | None,
    out: str | None,
    view: str = "art30",
    activities_path: str | None = None,
    signoff_path: str | None = None,
    explain_values: bool = False,
) -> int:
    fmt = _format(fmt, out)
    settings = config_module.load(config_module.find(config_path))
    # `--vocabulary` beats `vocabulary:` in the config, which beats the shipped
    # default. The flag is what someone reaches for while trying one out.
    words = vocabulary.load(vocabulary_path or settings.vocabulary or None)
    # Read before the events too: a typo in a document that asserts a lawful
    # basis should fail in the first millisecond, not after a long read.
    declared_uses = declared.load(activities_path, vocabulary=words) if activities_path else ()

    events, report = read(source, since=since, until=until)
    record = ropa.build(
        events,
        config=settings,
        vocabulary=words,
        report=report,
        since=since,
        until=until,
        declared=declared_uses,
        references=references_module.load(settings.references or None),
    )

    if not record.activities and not report.clean:
        # Nothing projected and something wrong reading: a failure, not an
        # empty record that looks like an answer.
        for reason in report.reasons():
            print(f"  {reason}", file=sys.stderr)
        return 1

    if view == "deployer":
        # Built from the Art. 30 record rather than from the events alone, so
        # the two views share purpose and legal basis instead of restating them.
        view_record = deployer.build(
            record,
            events,
            report=report,
            since=since,
            until=until,
        )
        return _emit(view_record, fmt=fmt, out=out, symbol=symbol, signoff_path=signoff_path)

    return _emit(
        record,
        fmt=fmt,
        out=out,
        symbol=symbol,
        signoff_path=signoff_path,
        explain_values=explain_values,
    )


def _quality(
    source: str,
    *,
    symbol: bool,
    since: datetime | None,
    until: datetime | None,
    domains: list[str],
    config_path: str | None,
    fmt: str | None,
    out: str | None,
    signoff_path: str | None = None,
) -> int:
    fmt = _format(fmt, out)
    settings = config_module.load(config_module.find(config_path))

    events, report = read(source, since=since, until=until)
    record = quality.build(
        events,
        config=settings,
        report=report,
        since=since,
        until=until,
        domains=domains,
    )

    if not record.datasets and not record.unchecked and not report.clean:
        for reason in report.reasons():
            print(f"  {reason}", file=sys.stderr)
        return 1

    return _emit(record, fmt=fmt, out=out, symbol=symbol, signoff_path=signoff_path)


def _provenance(
    source: str,
    *,
    symbol: bool,
    since: datetime | None,
    until: datetime | None,
    dataset: str,
    depth: int,
    config_path: str | None,
    fmt: str | None,
    out: str | None,
    signoff_path: str | None = None,
) -> int:
    fmt = _format(fmt, out)
    settings = config_module.load(config_module.find(config_path))

    events, report = read(source, since=since, until=until)
    events = list(events)

    # Nobody types the namespace, so a bare name is matched — but an ambiguous
    # one is handed back as a question. Picking the first would produce a chain
    # for a dataset the user did not ask about, and nothing downstream would
    # ever say so.
    matches = provenance.resolve(events, dataset)
    if not matches:
        raise ConfigError(
            f"no dataset named {dataset!r} appears in {report.origin or source} "
            "— check the spelling, or widen the window"
        )
    if len(matches) > 1:
        listed = "\n    ".join(matches)
        raise ConfigError(
            f"{dataset!r} matches more than one dataset. Name one in full:\n    {listed}"
        )

    record = provenance.build(
        events,
        dataset=matches[0],
        config=settings,
        report=report,
        since=since,
        until=until,
        depth=depth,
    )
    return _emit(record, fmt=fmt, out=out, symbol=symbol, signoff_path=signoff_path)


def _erasure(
    source: str,
    *,
    symbol: bool,
    since: datetime | None,
    until: datetime | None,
    dataset: str,
    depth: int,
    config_path: str | None,
    fmt: str | None,
    out: str | None,
    signoff_path: str | None = None,
) -> int:
    fmt = _format(fmt, out)
    settings = config_module.load(config_module.find(config_path))

    # Everything up to --until, not from --since on: what descends from the erased
    # dataset is known from runs before the erasure, and one nothing wrote since is
    # the descendant the record most needs to name. Read from --since, it was missing
    # instead. The tombstone and the writes measured against it take --since apart.
    events, report = read(source, until=until)
    events = list(events)

    # The same resolution `provenance` does, and for the same reason: nobody
    # types the namespace, and an ambiguous name is a question rather than a
    # silently wrong answer. Here a wrong answer would be a proof about the
    # wrong dataset, which is worse than no answer.
    matches = provenance.resolve(events, dataset)
    if not matches:
        raise ConfigError(
            f"no dataset named {dataset!r} appears in {report.origin or source} "
            "— check the spelling, or widen the window"
        )
    if len(matches) > 1:
        listed = "\n    ".join(matches)
        raise ConfigError(
            f"{dataset!r} matches more than one dataset. Name one in full:\n    {listed}"
        )

    record = erasure.build(
        events,
        dataset=matches[0],
        config=settings,
        report=report,
        since=since,
        until=until,
        depth=depth,
    )
    return _emit(record, fmt=fmt, out=out, symbol=symbol, signoff_path=signoff_path)


def _format(fmt: str | None, out: str | None) -> str:
    """Resolve the output format before a single event is read.

    An explicit `--format` wins; otherwise `--out history.md` means markdown
    and `--out history.xlsx` means a workbook. A combination that cannot work
    should fail in the first millisecond rather than after a long read against
    a remote backend.
    """
    fmt = fmt or render.infer(out)
    if render.is_binary(fmt) and not out:
        raise UsageError(
            f"--format {fmt} produces a file rather than text, and there is nowhere "
            f"to put it — add --out record.{fmt}"
        )
    return fmt


def _deliver(rendered, out: str | None) -> bool:
    """Print it or write it. Whether it earned a mark is not this function's business.

    Split out because a comparison has no verdict to report and must not borrow
    one — see cordata-tech/qedro#14. Returns whether it went to a file.
    """
    if not out:
        print(rendered, end="")
        return False

    path = Path(out)
    if isinstance(rendered, bytes):
        path.write_bytes(rendered)
    else:
        path.write_text(rendered, encoding="utf-8")
    return True


def _diff(before: str, after: str, *, fmt: str | None, out: str | None) -> int:
    """Two records, and what changed between them.

    No `--since` or `--until`: the window is whatever each document was built
    with, and re-cutting it here would be inventing coverage neither record has.
    """
    comparison = compare.compare(compare.read(before), compare.read(after))
    fmt = _format(fmt, out)
    renderer = render.FORMATS[fmt]
    if _deliver(renderer(comparison), out):
        found = len(comparison.changes)
        # A register disagreeing with a record has lost nothing — the two were
        # never in step — so the second half of this line has to say something
        # else or it would be telling the reader the wrong thing about it.
        detail = (
            f"{comparison.unchanged} entries agree throughout"
            if comparison.drift
            else f"{len(comparison.regressions)} a loss of evidence"
        )
        print(f"  wrote {out}  {found} findings, {detail}")
    # Cautions reach stderr even when the file was written, for the same reason
    # withheld reasons do: the run succeeded and the answer is still conditional.
    for caution in comparison.comparability.cautions():
        print(f"  ! {caution}", file=sys.stderr)
    return 0


def _demo(target: str) -> int:
    """Write the demo company and say what to run against it.

    The commands are printed rather than run: the point is that somebody types
    them, sees each output, and then types the same thing against their own
    lineage.
    """
    written = demo.write(Path(target))
    at = shlex.quote(target.rstrip("/"))
    # Both directories hold the same runs, so one of them is the count.
    events = sum(body.count("\n") for name, body in written.items() if name.startswith("lineage/"))
    print(
        f"  wrote {demo.CONTROLLER}, a company that does not exist, to {at}/\n"
        f"  {len(demo.PIPELINES)} pipelines over {demo.DAYS} days, {events:,} events, twice: "
        "the two directories differ only in whether each job declares its purpose\n"
        "\n"
        "  lineage alone, with purposes from the mapping file: no mark\n"
        f"    qedro ropa {at}/lineage --config {at}/qedro.yaml\n"
        "  the same pipelines, declaring their purpose: the record earns the mark\n"
        f"    qedro ropa {at}/lineage-declared --config {at}/qedro.yaml\n"
        "  which data-quality checks ran, and on which days they failed\n"
        f"    qedro quality {at}/lineage --config {at}/qedro.yaml\n"
        "  from a published table back to the commits that built it\n"
        f"    qedro provenance {at}/lineage --dataset billing_curated.dunning_cases\n"
        "  everything derived from an erased table, and whether the erasure reached it\n"
        f"    qedro erasure {at}/lineage-declared --dataset crm_raw.contacts "
        f"--config {at}/qedro.yaml\n"
        "  a register kept by hand, checked against the record\n"
        f"    qedro ropa {at}/lineage-declared --config {at}/qedro.yaml --out record.json\n"
        f"    qedro diff {at}/register.yaml record.json\n"
        "\n"
        "  Then run the same commands against your own lineage: a directory of "
        "OpenLineage events, or the URL of a Marquez-compatible API."
    )
    return 0


def _sign(record: str, *, state: str, by: str, note: str, config_path: str | None = None) -> int:
    """Add one sign-off entry beside a record's JSON (#40), with four eyes as
    qedro.yaml sets it (#47)."""
    settings = config_module.load(config_module.find(config_path))
    path, entry = signoff.sign(
        record,
        state=state,
        by=by,
        at=datetime.now(UTC).replace(microsecond=0),
        note=note,
        four_eyes=settings.four_eyes,
    )
    standing = signoff.load(path).standing(signoff.read_record(record))
    print(
        f"  {Path(record).name}: {standing.describe() if state == 'approved' else entry.describe()}"
    )
    print(f"  wrote {path}")
    return 0


def _status(directory: str) -> int:
    """Every record under *directory* and where its sign-off stands (#40).

    Read from the files alone: each record's JSON, hashed as `qedro sign` hashes
    it, against the sign-off file beside it. A JSON file that is not a record
    qedro wrote is counted rather than listed, as a directory read counts what
    it passed over.
    """
    root = Path(directory)
    if not root.is_dir():
        raise UsageError(f"no directory at {directory}")
    rows: list[tuple[str, str, str, str]] = []
    states: Counter[str] = Counter()
    passed_over = 0
    alone = 0
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith(".signoff.json"):
            continue
        try:
            payload = signoff.read_record(path)
        except UsageError:
            passed_over += 1
            continue
        if payload["qedro"].get("projection") == "status":
            # `qedro status --format json` written into the directory it reads.
            continue
        if signoff.kind(payload) not in signoff.COVERED:
            # A comparison is a record qedro wrote but not one anybody signs.
            passed_over += 1
            continue
        standing = signoff.load(signoff.sidecar(path)).standing(payload)
        states[standing.state] += 1
        if standing.second_person is False:
            alone += 1
        verdict = "mark earned" if payload.get("complete") else "mark withheld"
        rows.append(
            (str(path.relative_to(root)), str(payload["qedro"].get("projection", "")), verdict,
             standing.describe())
        )  # fmt: skip
    if not rows:
        print(f"  no records qedro wrote under {directory}")
    width = max((len(r[0]) for r in rows), default=0)
    for name, projection, verdict, standing in rows:
        print(f"  {name:<{width}}  {projection:<10}  {verdict:<13}  {standing}")
    if rows:
        counts = ", ".join(f"{states[s]} {s}" for s in signoff.STATES)
        print(f"\n  {words.count(len(rows), 'record')}: {counts}")
        if alone:
            print(
                f"  {words.count(alone, 'approval')} with no second person: the record was "
                "prepared and approved by the same person"
            )
        print(f"  a sign-off is {signoff.Standing.CAVEAT}")
    if passed_over:
        print(f"  {words.count(passed_over, 'JSON file')} passed over: not a record qedro wrote")
    return 0


#: The sign-off states a record counts as signed in, for `status --against`.
SIGNED = frozenset({"approved", "published"})


def _currency(
    directory: str,
    *,
    source: str | None,
    config_path: str | None = None,
    vocabulary_path: str | None = None,
    activities_path: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    regenerate_as: str | None = None,
    fmt: str = "text",
    out: str | None = None,
) -> int:
    """Whether each signed Art. 30 record still describes what runs (#42).

    One fresh record is built from *source*, as `qedro ropa` builds it, and
    every signed record under *directory* is compared with it activity by
    activity. A fresh run that cannot be built blocks every signed record, with
    the reason; it does not stop the command, since *we could not check* is a
    finding a reader needs as much as any other.

    With no *source*, only for `--format json`: every record and where its
    sign-off stands, compared with nothing — what the text `qedro status` prints.
    """
    root = Path(directory)
    if not root.is_dir():
        raise UsageError(f"no directory at {directory}")
    listed: list[tuple[Path, str, dict, signoff.Standing]] = []
    other = 0
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith(".signoff.json"):
            continue
        try:
            payload = signoff.read_record(path)
        except UsageError:
            continue
        if payload["qedro"].get("projection") == "status":
            # This command's own output, written into the directory it reads.
            continue
        kind = signoff.kind(payload)
        if kind not in signoff.COVERED or (source and kind != "ropa/art30"):
            # Only an Art. 30 record has activities a fresh run can be compared
            # with; the others are counted so the summary does not undersell.
            other += 1
            continue
        standing = signoff.load(signoff.sidecar(path)).standing(payload)
        listed.append((path, str(path.relative_to(root)), dict(payload), standing))
    signed = [row for row in listed if source and row[3].state in SIGNED]

    fresh: dict | None = None
    fresh_text = ""
    reason = ""
    # The fresh run's record and events, so each change can be given its cause (#49).
    attributor: attribution.Attributor | None = None
    if signed and source:
        try:
            settings = config_module.load(config_module.find(config_path))
            terms = vocabulary.load(vocabulary_path or settings.vocabulary or None)
            uses = declared.load(activities_path, vocabulary=terms) if activities_path else ()
            events, report = read(source, since=since, until=until)
            # An empty or unreadable source is not a platform where every job
            # stopped: compared with it, every activity would read as stale.
            # It is a comparison that could not be made, as `qedro ropa`
            # treats it.
            if not events:
                problems = "; ".join(report.reasons()) or "no events in it"
                raise UsageError(f"it read no events ({problems})")
            record = ropa.build(
                events,
                config=settings,
                vocabulary=terms,
                report=report,
                since=since,
                until=until,
                declared=uses,
                references=references_module.load(settings.references or None),
            )
            fresh_text = render.FORMATS["json"](record)
            fresh = json.loads(fresh_text)
            attributor = attribution.Attributor(record, events)
        except QedroError as exc:
            reason = f"the fresh run from {source} could not be built: {exc}"

    text = fmt != "json"
    totals = dict.fromkeys(staleness.STATES, 0)
    results: dict[str, tuple[staleness.RecordCheck, str | None]] = {}
    for path, origin, payload, standing in signed:
        result = (
            staleness.check(payload, fresh, origin=origin, attributor=attributor)
            if fresh is not None
            else staleness.blocked(origin, payload, reason)
        )
        for state, n in result.counts().items():
            totals[state] += n
        regenerated = None
        if regenerate_as and fresh is not None:
            regenerated = _regenerate(
                path, result, fresh, fresh_text, by=regenerate_as, source=source or "", echo=text
            )
        results[origin] = (result, regenerated)
        if text:
            print(f"  {origin}  {standing.describe()}")
            if result.blocked:
                print(f"    blocked: {result.blocked}")
            for caution in result.cautions:
                print(f"    ! {caution}")
            _print_states(result)

    if not text:
        document = {
            "qedro": render._document("status"),
            "directory": directory,
            # The fresh run's own scope rather than a timestamp: what it read,
            # over which window, is what says how current the comparison is.
            "against": None
            if not source
            else {
                "source": source,
                "window": (fresh or {}).get("scope", {}).get("window"),
                "blocked": reason or None,
            },
            "records": [
                {
                    "file": origin,
                    "projection": payload["qedro"].get("projection"),
                    "view": payload["qedro"].get("view"),
                    "complete": bool(payload.get("complete")),
                    "signoff": {
                        "state": standing.state,
                        "describe": standing.describe(),
                        "prepared_by": standing.prepared.by if standing.prepared else None,
                        "approved_by": standing.approved.by if standing.approved else None,
                        # `null` until approved; false when one person did both (#47).
                        "second_person": standing.second_person,
                    },
                    "check": staleness.check_json(results[origin][0])
                    if origin in results
                    else None,
                    "regenerated": results[origin][1] if origin in results else None,
                }
                for _, origin, payload, standing in listed
            ],
            "counts": totals if source else None,
            "not_compared": len(listed) - len(signed) if source else None,
            "other": other,
            "approved_without_second_person": sum(
                1 for *_, standing in listed if standing.second_person is False
            ),
        }
        _deliver(json.dumps(document, indent=2, ensure_ascii=False) + "\n", out)
        if out:
            print(f"  wrote {out}")
        return 0

    if not signed:
        print(f"  no signed Art. 30 records under {directory}")
    else:
        counts = ", ".join(f"{totals[s]} {s}" for s in staleness.STATES)
        print(f"\n  {words.count(len(signed), 'signed record')}: {counts}")
        if totals[staleness.STALE] or totals[staleness.NEW]:
            print("  the stale and new activities are the ones to send for sign-off again")
    unsigned = len(listed) - len(signed)
    if unsigned:
        print(f"  {words.count(unsigned, 'record')} not signed off, so not compared")
    if other:
        print(
            f"  {words.count(other, 'other record')} not compared: only an Art. 30 "
            "record has activities to compare"
        )
    return 0


def _regenerate(
    signed: Path,
    result: staleness.RecordCheck,
    fresh: dict,
    fresh_text: str,
    *,
    by: str,
    source: str,
    echo: bool = True,
) -> str | None:
    """Write the fresh record beside a signed one that changed, and send it for
    sign-off naming what changed (#55).

    The two writes the sign-off already allows: a record file, and one entry
    appended to the sign-off file. The signed record and its entries are not
    touched; `record.next.json` shares their sign-off file, so the history of
    both versions stays in one place.
    """
    stale = [a.key for a in result.activities if a.state == staleness.STALE]
    new = [a.key for a in result.activities if a.state == staleness.NEW]
    if result.blocked or not (stale or new):
        if echo:
            print("    not regenerated: " + ("blocked" if result.blocked else "up to date"))
        return None
    target = signoff.next_version(signed)
    target.write_text(fresh_text, encoding="utf-8")
    already = signoff.load(signoff.sidecar(target)).state(fresh)
    if already != "draft":
        # The same version was sent before, by this command or by hand; a
        # second identical entry would say nothing new.
        if echo:
            print(f"    wrote {target.name}; this version is already {already}")
        return target.name
    parts = []
    if stale:
        n = len(stale)
        parts.append(
            f"{n} {words.plural(n, 'stale activity', 'stale activities')} ({', '.join(stale)})"
        )
    if new:
        parts.append(f"{len(new)} new ({', '.join(new)})")
    note = f"regenerated by qedro status --against {source}: {'; '.join(parts)}"
    signoff.sign(target, state="for sign-off", by=by, at=datetime.now(UTC), note=note)
    if echo:
        print(f"    wrote {target.name}, sent for sign-off by {by}")
    return target.name


def _print_states(result: staleness.RecordCheck) -> None:
    """Stale, new and blocked activities by name with what changed; up to date as one line."""
    current = [a.key for a in result.activities if a.state == staleness.UP_TO_DATE]
    for a in result.activities:
        if a.state == staleness.UP_TO_DATE:
            continue
        print(f"    {a.state:<10}  {a.key}")
        if a.cause is not None:
            print(f"                  why: {a.cause.says}")
        for i, change in enumerate(a.changes):
            if change.kind == compare.REMOVED:
                print("                  not in the fresh run — it may not have run in the window")
            else:
                said, cost = render._finding(change)
                print(f"                  {change.label}: {said}" + (f" — {cost}" if cost else ""))
            # The cause under the change it explains, as far as the events show it (#49).
            if i < len(a.causes):
                print(f"                    why: {a.causes[i].says}")
    if current:
        print(f"    {staleness.UP_TO_DATE:<10}  {', '.join(current)}")


def _emit(
    record,
    *,
    fmt: str,
    out: str | None,
    symbol: bool,
    signoff_path: str | None = None,
    explain_values: bool = False,
) -> int:
    """Render and deliver, the same way for every projection."""
    if signoff_path:
        # Against the record as built from these events, not as somebody saved
        # it: a sign-off covers this version only if nothing it states changed.
        if not Path(signoff_path).is_file():
            raise UsageError(f"no sign-off file at {signoff_path}")
        payload = json.loads(render.FORMATS["json"](record))
        record.signoff = signoff.standing_of(payload, signoff_path)
    renderer = render.FORMATS[fmt]
    rendered = renderer(record, symbol=symbol) if fmt == "text" else renderer(record)
    # On request only in text and Markdown, which a person reads top to bottom
    # and which a sentence per value would bury (#48). The other formats always
    # carry them, where they sit apart from the record's own lines.
    if explain_values and fmt in ("text", "markdown"):
        rendered += render.explanations(record, markdown=fmt == "markdown")

    if not _deliver(rendered, out):
        return 0

    mark = record.completeness.suffix(symbol=symbol)
    print(f"  wrote {out}{'  ' + mark if mark else ''}")
    # Reasons go to stderr even when the file was written. The run succeeded;
    # the artefact simply does not claim to be a proof.
    for reason in record.completeness.reasons:
        print(f"  ! {reason}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Shared flags go on a parent parser so they are accepted on either side
    # of the subcommand. `qedro events ./ --no-symbol` is how people actually
    # type it, and rejecting that is a papercut nobody reports, they just stop.
    #
    # SUPPRESS as the default matters: without it the subparser's default
    # overwrites a value already set at the top level, and the flag silently
    # does nothing when written before the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--no-symbol",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print [complete] instead of the tombstone, for terminals with no glyph for U+220E",
    )

    parser = argparse.ArgumentParser(
        prog="qedro",
        parents=[common],
        description="Turns emitted evidence into the artefacts an auditor asks for.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"qedro {__version__}")

    sub = parser.add_subparsers(dest="command")
    events = sub.add_parser(
        "events",
        parents=[common],
        help="read OpenLineage events from a directory or an API and summarise them",
    )
    events.add_argument(
        "source",
        help=SOURCE_HELP,
    )
    events.add_argument("--since", type=_instant, help="ignore events before this date")
    events.add_argument("--until", type=_instant, help="ignore events after this date")

    ropa_cmd = sub.add_parser(
        "ropa",
        parents=[common],
        help="produce a GDPR Art. 30 record of processing activities",
    )
    ropa_cmd.add_argument(
        "source",
        help=SOURCE_HELP,
    )
    ropa_cmd.add_argument("--since", type=_instant, help="ignore events before this date")
    ropa_cmd.add_argument("--until", type=_instant, help="ignore events after this date")
    ropa_cmd.add_argument(
        "--config",
        help="qedro.yaml (or .json/.toml). Defaults to one beside the working directory",
    )
    ropa_cmd.add_argument(
        "--vocabulary",
        help="a vocabulary document to read terms from, instead of the shipped GDPR baseline",
    )
    ropa_cmd.add_argument(
        "--format",
        dest="fmt",
        choices=sorted(render.names()),
        default=None,
        help="output format. Defaults to the one implied by --out, else text",
    )
    ropa_cmd.add_argument("--out", help="write to this file instead of standard output")
    ropa_cmd.add_argument(
        "--signoff",
        metavar="FILE",
        help="print where this record stands against a sign-off file `qedro sign` wrote",
    )
    ropa_cmd.add_argument(
        "--view",
        choices=("art30", "deployer"),
        default="art30",
        help="art30: the GDPR Art. 30 record (default). deployer: the same record, "
        "per AI use case, with the model version, inputs and run records a deployer "
        "under the AI Act is asked about",
    )
    ropa_cmd.add_argument(
        "--activities",
        metavar="PATH",
        help="a document of declared activities — processing that emits no lineage. "
        "Marked as declared in the output, and never counted as evidence",
    )
    ropa_cmd.add_argument(
        "--explain",
        action="store_true",
        help="add where each value came from, in a sentence, and the requirement it answers "
        "to text and markdown output. JSON, PDF and xlsx always carry them",
    )

    quality_cmd = sub.add_parser(
        "quality",
        parents=[common],
        help="what was asserted about each dataset, and what was never checked",
    )
    quality_cmd.add_argument(
        "source",
        help=SOURCE_HELP,
    )
    quality_cmd.add_argument("--since", type=_instant, help="ignore events before this date")
    quality_cmd.add_argument("--until", type=_instant, help="ignore events after this date")
    quality_cmd.add_argument(
        "--days",
        type=int,
        help="shorthand for --since N days before --until (or before now)",
    )
    quality_cmd.add_argument(
        "--domain",
        action="append",
        default=[],
        dest="domains",
        metavar="NAME",
        help="only datasets in this domain. Repeatable",
    )
    quality_cmd.add_argument(
        "--config",
        help="qedro.yaml (or .json/.toml). Defaults to one beside the working directory",
    )
    quality_cmd.add_argument(
        "--format",
        dest="fmt",
        choices=sorted(render.names()),
        default=None,
        help="output format. Defaults to the one implied by --out, else text",
    )
    quality_cmd.add_argument("--out", help="write to this file instead of standard output")
    quality_cmd.add_argument(
        "--signoff",
        metavar="FILE",
        help="print where this record stands against a sign-off file `qedro sign` wrote",
    )

    provenance_cmd = sub.add_parser(
        "provenance",
        parents=[common],
        help="the chain from a dataset back to the commits that produced it",
    )
    provenance_cmd.add_argument(
        "source",
        help=SOURCE_HELP,
    )
    provenance_cmd.add_argument(
        "--dataset",
        required=True,
        help="the dataset to trace. A bare name is enough unless it is ambiguous",
    )
    provenance_cmd.add_argument(
        "--depth",
        type=int,
        default=provenance.DEPTH,
        help=f"how many hops upstream to follow (default {provenance.DEPTH})",
    )
    provenance_cmd.add_argument("--since", type=_instant, help="ignore events before this date")
    provenance_cmd.add_argument("--until", type=_instant, help="ignore events after this date")
    provenance_cmd.add_argument(
        "--days",
        type=int,
        help="shorthand for --since N days before --until (or before now)",
    )
    provenance_cmd.add_argument(
        "--config",
        help="qedro.yaml (or .json/.toml). Defaults to one beside the working directory",
    )
    provenance_cmd.add_argument(
        "--format",
        dest="fmt",
        choices=sorted(render.names()),
        default=None,
        help="output format. Defaults to the one implied by --out, else text",
    )
    provenance_cmd.add_argument("--out", help="write to this file instead of standard output")
    provenance_cmd.add_argument(
        "--signoff",
        metavar="FILE",
        help="print where this record stands against a sign-off file `qedro sign` wrote",
    )

    erasure_cmd = sub.add_parser(
        "erasure",
        parents=[common],
        help="what descends from an erased dataset, and whether the erasure reached it",
        description=(
            "Walks the lineage graph forwards from a dataset somebody erased and reports "
            "every dataset derived from it, with whether a job rewrote each one "
            "afterwards. It reports datasets and not rows: no lineage event says that a "
            "particular data subject's rows are gone, and this never claims otherwise."
        ),
    )
    erasure_cmd.add_argument(
        "source",
        help=SOURCE_HELP,
    )
    erasure_cmd.add_argument(
        "--dataset",
        required=True,
        help="the dataset that was erased. A bare name is matched where it is unambiguous",
    )
    erasure_cmd.add_argument(
        "--since",
        type=_instant,
        help="when the erasure was requested. Events before it are still read, since "
        "they say what descends from the erased dataset. The first "
        "completed run after it that emitted a lifecycleStateChange drop, truncate or "
        "overwrite supersedes it, as evidence rather than an assertion, with a drop or "
        "truncate preferred over an overwrite",
    )
    erasure_cmd.add_argument("--until", type=_instant, help="ignore events after this date")
    erasure_cmd.add_argument(
        "--days",
        type=int,
        help="shorthand for --since N days before --until (or before now)",
    )
    erasure_cmd.add_argument(
        "--depth",
        type=int,
        default=erasure.DEPTH,
        help=f"how many hops downstream to follow (default {erasure.DEPTH})",
    )
    erasure_cmd.add_argument(
        "--config",
        help="qedro.yaml (or .json/.toml). Defaults to one beside the working directory",
    )
    erasure_cmd.add_argument(
        "--format",
        dest="fmt",
        choices=sorted(render.names()),
        default=None,
        help="output format. Defaults to the one implied by --out, else text",
    )
    erasure_cmd.add_argument("--out", help="write to this file instead of standard output")
    erasure_cmd.add_argument(
        "--signoff",
        metavar="FILE",
        help="print where this record stands against a sign-off file `qedro sign` wrote",
    )

    diff_cmd = sub.add_parser(
        "diff",
        parents=[common],
        help="what changed between two records, from their JSON output",
        description=(
            "Compares two JSON records this tool produced — a before and an after that "
            "a team keeps in Git, with no database between them. Reports a purpose that "
            "stopped being emitted even when its value did not change, and prints no "
            "mark of its own: it cannot verify either document. Hand one side a "
            "register instead (a YAML, JSON or TOML document with a `register:` mapping) "
            "and it reports where that register and the record disagree."
        ),
    )
    diff_cmd.add_argument(
        "before", help="the earlier record as JSON, or a register (#24) in either position"
    )
    diff_cmd.add_argument("after", help="the later record, as JSON")
    diff_cmd.add_argument(
        "--format",
        dest="fmt",
        choices=sorted(render.names()),
        default=None,
        help="output format. Defaults to the one implied by --out, else text",
    )
    diff_cmd.add_argument("--out", help="write to this file instead of standard output")

    demo_cmd = sub.add_parser(
        "demo",
        help="write a fictional company's lineage and documents, to run the projections against",
        description=(
            "Writes three weeks of OpenLineage from a company that does not exist, with "
            "the configuration, declared activities and register that go with it, and "
            "prints the commands that show each projection. Nothing is read or sent "
            "anywhere. Refuses a directory that already has anything in it."
        ),
    )
    demo_cmd.add_argument(
        "directory", nargs="?", default="demo", help="where to write it (default ./demo)"
    )

    sign_cmd = sub.add_parser(
        "sign",
        help="record a person's sign-off on a record's JSON, in a file beside it",
        description=(
            "Adds one entry to record.signoff.json beside record.json: the state, who "
            "set it, when, and the SHA-256 of the record it covers. The states are "
            "draft, for sign-off, approved and published, one step forward at a time "
            "or back to draft, and nothing already in the file is changed. A sign-off "
            "is a person's acceptance of the record, not evidence, and never changes "
            "its verdict."
        ),
    )
    sign_cmd.add_argument("record", help="the record's JSON, as --out record.json wrote it")
    sign_cmd.add_argument("--as", dest="by", required=True, help="who is signing, by name")
    sign_cmd.add_argument(
        "--state", required=True, choices=list(signoff.STATES), help="the state to move to"
    )
    sign_cmd.add_argument("--note", default="", help="a sentence kept with the entry")
    sign_cmd.add_argument(
        "--config",
        help="qedro.yaml, for `signoff: {four_eyes: false}`. Defaults to one beside the working "
        "directory; without one, four eyes is on",
    )

    status_cmd = sub.add_parser(
        "status",
        help="every record in a directory and where its sign-off stands",
        description=(
            "Lists each record qedro wrote under a directory, whether it earned the "
            "mark, and its sign-off, read from the files beside it. A record changed "
            "since it was signed is reported as not signed off, naming the earlier "
            "sign-off."
        ),
    )
    status_cmd.add_argument("directory", nargs="?", default=".", help="where the records are")
    status_cmd.add_argument(
        "--against",
        metavar="SOURCE",
        help="also build a fresh record from this lineage source and say, for each activity "
        "of every signed Art. 30 record, whether it is up to date, stale, new or blocked",
    )
    status_cmd.add_argument("--config", help="qedro.yaml for the fresh run")
    status_cmd.add_argument("--vocabulary", help="a vocabulary document for the fresh run")
    status_cmd.add_argument(
        "--activities", metavar="PATH", help="declared activities for the fresh run"
    )
    status_cmd.add_argument(
        "--regenerate",
        action="store_true",
        help="with --against: write the fresh record beside each signed one that has a stale "
        "or new activity, as <record>.next.json, and send it for sign-off naming what changed",
    )
    status_cmd.add_argument(
        "--as", dest="by", metavar="NAME", help="who is regenerating, for the sign-off entry"
    )
    status_cmd.add_argument(
        "--format",
        dest="fmt",
        choices=["text", "json"],
        default="text",
        help="json writes every record, its sign-off and, with --against, each activity's "
        "state, for a reader such as the console",
    )
    status_cmd.add_argument("--out", help="write to this file instead of standard output")
    status_cmd.add_argument("--since", type=_instant, help="the fresh run ignores events before")
    status_cmd.add_argument("--until", type=_instant, help="the fresh run ignores events after")

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # The env var is for CI logs and containers, where nobody is around to
    # pass a flag and a tofu box reads as a bug in the tool.
    no_symbol = getattr(args, "no_symbol", False) or os.environ.get("QEDRO_NO_SYMBOL") == "1"

    try:
        if args.command == "events":
            return _events(args.source, symbol=not no_symbol, since=args.since, until=args.until)
        if args.command == "quality":
            since, until = _window(args)
            return _quality(
                args.source,
                symbol=not no_symbol,
                since=since,
                until=until,
                domains=args.domains,
                config_path=args.config,
                fmt=args.fmt,
                out=args.out,
                signoff_path=args.signoff,
            )
        if args.command == "provenance":
            since, until = _window(args)
            return _provenance(
                args.source,
                symbol=not no_symbol,
                since=since,
                until=until,
                dataset=args.dataset,
                depth=args.depth,
                config_path=args.config,
                fmt=args.fmt,
                out=args.out,
                signoff_path=args.signoff,
            )
        if args.command == "erasure":
            since, until = _window(args)
            return _erasure(
                args.source,
                symbol=not no_symbol,
                since=since,
                until=until,
                dataset=args.dataset,
                depth=args.depth,
                config_path=args.config,
                fmt=args.fmt,
                out=args.out,
                signoff_path=args.signoff,
            )
        if args.command == "demo":
            return _demo(args.directory)
        if args.command == "sign":
            return _sign(
                args.record, state=args.state, by=args.by, note=args.note, config_path=args.config
            )
        if args.command == "status":
            if args.regenerate and not args.against:
                raise UsageError("--regenerate needs --against: a record is rebuilt from a source")
            if args.regenerate and not (args.by or "").strip():
                raise UsageError(
                    "--regenerate sends a new version for sign-off, which names who did it "
                    "— add --as 'Erika Mustermann'"
                )
            if args.against:
                return _currency(
                    args.directory,
                    source=args.against,
                    config_path=args.config,
                    vocabulary_path=args.vocabulary,
                    activities_path=args.activities,
                    since=args.since,
                    until=args.until,
                    regenerate_as=args.by.strip() if args.regenerate else None,
                    fmt=args.fmt,
                    out=args.out,
                )
            if args.fmt == "json":
                return _currency(args.directory, source=None, fmt="json", out=args.out)
            return _status(args.directory)
        if args.command == "diff":
            return _diff(args.before, args.after, fmt=args.fmt, out=args.out)
        if args.command == "ropa":
            return _ropa(
                args.source,
                symbol=not no_symbol,
                since=args.since,
                until=args.until,
                config_path=args.config,
                vocabulary_path=args.vocabulary,
                fmt=args.fmt,
                out=args.out,
                view=args.view,
                activities_path=args.activities,
                signoff_path=args.signoff,
                explain_values=args.explain,
            )
    except QedroError as exc:
        # What the user wrote, handed back as a sentence rather than a
        # traceback. Evidence never gets here — it is counted, not raised.
        print(f"  {exc}", file=sys.stderr)
        return 2

    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
