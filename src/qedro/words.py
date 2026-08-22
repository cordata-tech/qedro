"""Saying a number correctly.

`1 file`, not `1 files`. `1 of 4 activities relies`, not `1 of 4 activities
rely`. Small, and the kind of small that costs a tool its authority: an
artefact whose whole argument is that its numbers should be taken seriously
cannot print a verb that disagrees with one.

This lived in three places before it lived here — the CLI summary line, the
completeness reasons, and the workbook's verdict — which is two more than the
number of times anybody would remember to fix it.
"""

from __future__ import annotations


def count(n: int, noun: str) -> str:
    """`1 file`, `2 files`, `1,284 events`."""
    return f"{n:,} {noun if n == 1 else noun + 's'}"


def plural(n: int, singular: str, plural: str) -> str:
    """Pick the form that agrees with *n*.

    Both forms are spelled out rather than derived, because English does not
    derive them — *relies*/*rely* and *has*/*have* are the cases this exists
    for, and appending an `s` gets both backwards.

    Note that in `n of m`, the noun agrees with *m* and the verb with *n*, so
    the two are asked for separately.
    """
    return singular if n == 1 else plural
