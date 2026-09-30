"""Writes the demo into `demo/`, from the generator `qedro demo` uses.

The generator and the three hand-written documents live in `qedro.demo`, so
that an installed package can produce the demo without the repository. This
writes the same files here so they can be read on GitHub and linked from the
README, and `--check` keeps the two from drifting.

Usage::

    python tools/seed.py            # rewrite demo/
    python tools/seed.py --check    # fail if demo/ is out of date
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from qedro import demo

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; fail if what is committed differs from what this would produce",
    )
    args = parser.parse_args(argv)

    stale = []
    for name, body in demo.files().items():
        path = DEMO / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != body:
                stale.append(path.relative_to(ROOT))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    if args.check:
        if stale:
            print("out of date, run `python tools/seed.py`:", file=sys.stderr)
            for path in stale:
                print(f"  {path}", file=sys.stderr)
            return 1
        print("demo/ is current")
        return 0

    print(f"wrote {len(demo.files())} files in {DEMO.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
