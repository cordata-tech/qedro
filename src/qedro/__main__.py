"""CLI entry point. The projections are not built yet."""

from __future__ import annotations

import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in {"-V", "--version"}:
        print(f"qedro {__version__}")
        return 0
    print(
        "qedro — turns emitted evidence into the artefacts an auditor asks for.\n"
        "\n"
        "Nothing is wired up yet. The event reader is the current work; see\n"
        "https://github.com/cordata-tech/qedro for what is planned.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
