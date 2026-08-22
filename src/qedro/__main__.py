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
from datetime import datetime
from pathlib import Path

from . import __version__, render, ropa, vocabulary
from . import config as config_module
from .errors import QedroError, UsageError
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


def _count(n: int, noun: str) -> str:
    """`1 file`, not `1 files`.

    Small, and the kind of small that costs a tool its authority. An artefact
    that argues for care about what a number means cannot print a plural it
    does not mean.
    """
    return f"{n:,} {noun if n == 1 else noun + 's'}"


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
    fetched = _count(report.files, "file") if report.files else _count(report.pages, "page")
    summary = " · ".join(
        [
            _count(report.events, "event"),
            _count(len(jobs), "job"),
            _count(len(datasets), "dataset"),
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
) -> int:
    # Resolved first, before a single event is read. An explicit `--format`
    # wins; otherwise `--out ropa.md` means markdown and `--out ropa.xlsx`
    # means a workbook. A combination that cannot work should fail in the first
    # millisecond rather than after a long read against a remote backend.
    fmt = fmt or render.infer(out)
    if render.is_binary(fmt) and not out:
        raise UsageError(
            f"--format {fmt} produces a file rather than text, and there is nowhere "
            f"to put it — add --out record.{fmt}"
        )

    settings = config_module.load(config_module.find(config_path))
    # `--vocabulary` beats `vocabulary:` in the config, which beats the shipped
    # default. The flag is what someone reaches for while trying one out.
    words = vocabulary.load(vocabulary_path or settings.vocabulary or None)

    events, report = read(source, since=since, until=until)
    record = ropa.build(
        events,
        config=settings,
        vocabulary=words,
        report=report,
        since=since,
        until=until,
    )

    if not record.activities and not report.clean:
        # Nothing projected and something wrong reading: a failure, not an
        # empty record that looks like an answer.
        for reason in report.reasons():
            print(f"  {reason}", file=sys.stderr)
        return 1

    renderer = render.FORMATS[fmt]
    rendered = renderer(record, symbol=symbol) if fmt == "text" else renderer(record)

    if out:
        path = Path(out)
        if isinstance(rendered, bytes):
            path.write_bytes(rendered)
        else:
            path.write_text(rendered, encoding="utf-8")
        mark = record.completeness.suffix(symbol=symbol)
        print(f"  wrote {out}{'  ' + mark if mark else ''}")
        # Reasons go to stderr even when the file was written. The run
        # succeeded; the artefact simply does not claim to be a proof.
        for reason in record.completeness.reasons:
            print(f"  ! {reason}", file=sys.stderr)
    else:
        print(rendered, end="")

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
        help="produce a DSGVO Art. 30 record of processing activities",
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
        help="a vocabulary document to read terms from, instead of the shipped DSGVO baseline",
    )
    ropa_cmd.add_argument(
        "--format",
        dest="fmt",
        choices=sorted(render.names()),
        default=None,
        help="output format. Defaults to the one implied by --out, else text",
    )
    ropa_cmd.add_argument("--out", help="write to this file instead of standard output")

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # The env var is for CI logs and containers, where nobody is around to
    # pass a flag and a tofu box reads as a bug in the tool.
    no_symbol = getattr(args, "no_symbol", False) or os.environ.get("QEDRO_NO_SYMBOL") == "1"

    try:
        if args.command == "events":
            return _events(args.source, symbol=not no_symbol, since=args.since, until=args.until)
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
