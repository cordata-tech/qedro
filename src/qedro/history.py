"""When a line of the mapping file last changed, read from Git (#49).

A mapping rule is an assertion somebody wrote. When a record changes because a
rule did, a reviewer asks who changed it and when, and where `qedro.yaml` is kept
in Git, its history answers that. This reads it: `git log -L` on the rule's line,
for the commit that last changed it.

Reading only, in the file's own repository, with nothing that would make Git run a
command the repository configures — no fsmonitor, no external diff, no text
conversion, no pager, no prompt. Git is not a dependency: where it is missing,
the file is not in a repository, or the line has uncommitted changes, the answer
is that history is not available and why, never a guess and never an error.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

#: Settings that would otherwise let a repository's own config run a program
#: while qedro reads it.
SAFE = (
    "-c", "core.fsmonitor=",
    "-c", "core.hooksPath=/dev/null",
    "-c", "diff.external=",
    "--no-pager",
)  # fmt: skip

#: Long enough for a large repository on a slow disk; a read that takes longer is
#: reported as unavailable rather than holding the command up.
TIMEOUT = 10


@dataclass(frozen=True)
class LineChange:
    """The commit that last changed one line of a file."""

    commit: str
    when: str
    author: str
    subject: str


@dataclass(frozen=True)
class Unavailable:
    """Why the history of a line could not be read."""

    reason: str


def _git(directory: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    git = shutil.which("git")
    if git is None:
        return None
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    try:
        return subprocess.run(
            [git, *SAFE, "-C", str(directory), *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def block_end(file: str, line: int) -> int:
    """The last line of the entry that starts at *line*: it and every line after it
    that is blank or indented further, so a rule's purpose, written under its
    pattern, is part of the rule. *line* itself where the file cannot be read."""
    try:
        lines = Path(file).read_text(encoding="utf-8").splitlines()
    except OSError:
        return line
    if not 1 <= line <= len(lines):
        return line

    def indent(text: str) -> int:
        return len(text) - len(text.lstrip())

    head = indent(lines[line - 1])
    end = line
    for number in range(line + 1, len(lines) + 1):
        text = lines[number - 1]
        if not text.strip():
            continue
        if indent(text) <= head:
            break
        end = number
    return end


@lru_cache(maxsize=256)
def line_change(file: str, line: int, end: int | None = None) -> LineChange | Unavailable:
    """The commit that last changed lines *line* to *end* of *file* (one line where
    *end* is not given), or why it cannot be said."""
    path = Path(file)
    if not path.is_file():
        return Unavailable(f"{file} is not a file qedro can read here")
    directory, name = path.resolve().parent, path.name
    if shutil.which("git") is None:
        return Unavailable("git is not installed, so the file's history cannot be read")

    inside = _git(directory, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
        return Unavailable(f"{file} is not in a Git repository")
    tracked = _git(directory, "ls-files", "--error-unmatch", "--", name)
    if tracked is None or tracked.returncode != 0:
        return Unavailable(f"{file} is not committed to its repository")
    dirty = _git(directory, "diff", "--quiet", "--no-ext-diff", "--no-textconv", "HEAD", "--", name)
    if dirty is None or dirty.returncode not in (0, 1):
        return Unavailable(f"the history of {file} could not be read")
    if dirty.returncode == 1:
        return Unavailable(
            f"{file} has uncommitted changes, so its history may not hold the one that matters"
        )

    log = _git(
        directory,
        "log",
        "-1",
        "--no-ext-diff",
        "--no-textconv",
        "-s",
        "--format=%H%x1f%aI%x1f%an%x1f%s",
        f"-L{line},{end or line}:{name}",
    )
    if log is None or log.returncode != 0 or not log.stdout.strip():
        return Unavailable(f"the history of line {line} of {file} could not be read")
    commit, when, author, subject = (log.stdout.strip().splitlines()[0].split("\x1f") + [""] * 4)[
        :4
    ]
    return LineChange(commit=commit, when=when, author=author, subject=subject)
