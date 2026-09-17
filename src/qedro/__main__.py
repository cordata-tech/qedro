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
import os
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import __version__, declared, deployer, provenance, quality, render, ropa, vocabulary, words
from . import config as config_module
from .errors import ConfigError, QedroError, UsageError
from .mark import Completeness
from .sources import read


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
        return 1

    by_type = Counter(e.event_type for e in events)
    jobs = {e.job.key for e in events}
    datasets = {d.key for e in events for d in e.datasets}

    # One of the two is always zero — a directory has files and an API has
    # pages, and naming the wrong one reads as a bug in the tool.
    fetched = (
        words.count(report.files, "file") if report.files else words.count(report.pages, "page")
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
        return _emit(view_record, fmt=fmt, out=out, symbol=symbol)

    return _emit(record, fmt=fmt, out=out, symbol=symbol)


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

    return _emit(record, fmt=fmt, out=out, symbol=symbol)


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
    return _emit(record, fmt=fmt, out=out, symbol=symbol)


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


def _emit(record, *, fmt: str, out: str | None, symbol: bool) -> int:
    """Render and deliver, the same way for every projection."""
    renderer = render.FORMATS[fmt]
    rendered = renderer(record, symbol=symbol) if fmt == "text" else renderer(record)

    if not out:
        print(rendered, end="")
        return 0

    path = Path(out)
    if isinstance(rendered, bytes):
        path.write_bytes(rendered)
    else:
        path.write_text(rendered, encoding="utf-8")

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
        help="a directory of .json, .ndjson or .jsonl events, "
        "or the base URL of a Marquez-compatible API",
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
        help="a directory of .json, .ndjson or .jsonl events, "
        "or the base URL of a Marquez-compatible API",
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

    quality_cmd = sub.add_parser(
        "quality",
        parents=[common],
        help="what was asserted about each dataset, and what was never checked",
    )
    quality_cmd.add_argument(
        "source",
        help="a directory of .json, .ndjson or .jsonl events, "
        "or the base URL of a Marquez-compatible API",
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

    provenance_cmd = sub.add_parser(
        "provenance",
        parents=[common],
        help="the chain from a dataset back to the commits that produced it",
    )
    provenance_cmd.add_argument(
        "source",
        help="a directory of .json, .ndjson or .jsonl events, "
        "or the base URL of a Marquez-compatible API",
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
            )
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
