"""CLI entry point.

One command so far. ``qedro events`` reads a directory and says what it
found — not a projection, and it does not pretend to be one, but it is the
thing to run first to find out whether your lineage is readable at all.

The projections come next. This exists so the reader is usable before they
land, and so the completeness rule is exercised end to end rather than only
in tests.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

from . import __version__
from .mark import Completeness
from .sources import read_dir


def _events(path: str, *, symbol: bool) -> int:
    events, report = read_dir(path)

    completeness = Completeness()
    for reason in report.reasons():
        completeness = completeness.degraded(reason)

    if not events and not report.clean:
        # Nothing read and something wrong: a failure, not a quiet success
        # with an empty result.
        for reason in report.reasons():
            print(f"  {reason}", file=sys.stderr)
        return 1

    by_type = Counter(e.event_type for e in events)
    jobs = {e.job.key for e in events}
    datasets = {d.key for e in events for d in e.datasets}

    summary = " · ".join(
        [
            f"{report.events} events",
            f"{len(jobs)} jobs",
            f"{len(datasets)} datasets",
            f"{report.files} files",
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
        help="read a directory of OpenLineage events and summarise it",
    )
    events.add_argument("path", help="directory containing .json, .ndjson or .jsonl events")

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    # The env var is for CI logs and containers, where nobody is around to
    # pass a flag and a tofu box reads as a bug in the tool.
    no_symbol = getattr(args, "no_symbol", False) or os.environ.get("QEDRO_NO_SYMBOL") == "1"

    if args.command == "events":
        return _events(args.path, symbol=not no_symbol)

    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
