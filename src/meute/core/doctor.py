"""The pure core of `meute doctor`: version parsing, checks, rendering and exit code.

The probes (running tools, reading the files) live in the CLI; everything here is a function of
the text they gathered.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from meute.core.text import printable

_VERSION = re.compile(r"[0-9]{1,9}(?:\.[0-9]{1,9})+")
_OPTION = re.compile(r"--[a-z][a-z-]*")
_SHOWN_MAX = 40
_TMUX_MIN = (3, 2)
_TMUX_META_T = (3, 3)
_GIT_MIN = (2, 36)
_CLAUDE_MIN = (2, 1, 301)
_CLAUDE_OPTIONS = (
    "--settings",
    "--mcp-config",
    "--session-id",
    "--resume",
    "--permission-mode",
    "--append-system-prompt",
)
_GIT_NEED = "worktrees and the Git line need git 2.36 or later"
_TMUX_NEED = "meute needs tmux 3.2 or later"


class CheckLevel(StrEnum):
    """How a line of `meute doctor` weighs: only `FAIL` changes the exit code."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    NOTE = "note"


@dataclass(frozen=True, slots=True, kw_only=True)
class Check:
    """One line of `meute doctor`."""

    level: CheckLevel
    name: str
    text: str


NOTE_CHECK = Check(
    level=CheckLevel.NOTE,
    name="note",
    text=(
        "--append-system-prompt-file (used above 8000 bytes of context) is not in claude --help "
        "and cannot be checked"
    ),
)


def parse_version(output: str) -> tuple[int, ...] | None:
    """Return the first dotted number of the first line of `output`, or None."""
    first = output.splitlines()[0] if output else ""
    found = _VERSION.search(first)
    return tuple(int(part) for part in found.group().split(".")) if found else None


def shown_version(output: str, prefix: str) -> str:
    """Return the first line of `output` without `prefix`, printable and cut to 40 characters."""
    first = output.splitlines()[0].strip() if output.strip() else ""
    return printable(first.removeprefix(prefix))[:_SHOWN_MAX]


def _unreadable(name: str, output: str, level: CheckLevel) -> Check:
    return Check(level=level, name=name, text=f"unreadable version: {shown_version(output, '')}")


def tmux_check(output: str | None) -> Check:
    """Judge the output of `tmux -V` (None: tmux was not found)."""
    if output is None:
        return Check(level=CheckLevel.FAIL, name="tmux", text=f"not found: {_TMUX_NEED}")
    version = parse_version(output)
    if version is None:
        return _unreadable("tmux", output, CheckLevel.FAIL)
    shown = shown_version(output, "tmux ")
    if version < _TMUX_MIN:
        return Check(level=CheckLevel.FAIL, name="tmux", text=f"{shown}: {_TMUX_NEED}")
    if version < _TMUX_META_T:
        text = f"{shown}: M-t needs tmux 3.3 or later"
        return Check(level=CheckLevel.WARN, name="tmux", text=text)
    return Check(level=CheckLevel.OK, name="tmux", text=shown)


def git_check(output: str | None) -> Check:
    """Judge the output of `git --version` (None: git was not found)."""
    if output is None:
        return Check(level=CheckLevel.FAIL, name="git", text=f"not found: {_GIT_NEED}")
    version = parse_version(output)
    if version is None:
        return _unreadable("git", output, CheckLevel.FAIL)
    shown = shown_version(output, "git version ")
    if version < _GIT_MIN:
        return Check(level=CheckLevel.FAIL, name="git", text=f"{shown}: {_GIT_NEED}")
    return Check(level=CheckLevel.OK, name="git", text=shown)


def claude_check(output: str | None) -> Check:
    """Judge the output of `claude --version` (None: claude was not found)."""
    if output is None:
        text = "not found: Claude sessions are disabled"
        return Check(level=CheckLevel.FAIL, name="claude", text=text)
    version = parse_version(output)
    if version is None:
        return _unreadable("claude", output, CheckLevel.WARN)
    shown = shown_version(output, "")
    if version < _CLAUDE_MIN:
        text = f"{shown}: meute is tested with claude 2.1.301 or later"
        return Check(level=CheckLevel.WARN, name="claude", text=text)
    return Check(level=CheckLevel.OK, name="claude", text=shown)


def options_check(help_text: str) -> Check:
    """Check that `claude --help` lists every option meute passes, comparing whole words."""
    listed = set(_OPTION.findall(help_text))
    missing = [option for option in _CLAUDE_OPTIONS if option not in listed]
    if missing:
        text = f"claude --help does not list: {', '.join(missing)}"
        return Check(level=CheckLevel.FAIL, name="options", text=text)
    text = "claude --help lists every option meute uses"
    return Check(level=CheckLevel.OK, name="options", text=text)


def timeout_check(name: str) -> Check:
    """Return the failure for the tool `name` that did not answer within 5 s."""
    return Check(level=CheckLevel.FAIL, name=name, text=f"{name} did not answer within 5 s")


def database_check(shown: str, version: int | None, latest: int) -> Check:
    """Compare the schema `version` of the database at `shown` (None: absent) with `latest`."""
    if version is None:
        text = f"{shown}: created at the first start"
        return Check(level=CheckLevel.WARN, name="database", text=text)
    text = f"{shown} (schema {version})"
    if version < latest:
        return Check(
            level=CheckLevel.WARN, name="database", text=f"{text}: migrated at the next start"
        )
    if version > latest:
        text = f"{text}: newer than this meute ({latest})"
        return Check(level=CheckLevel.FAIL, name="database", text=text)
    return Check(level=CheckLevel.OK, name="database", text=text)


def render_checks(checks: Sequence[Check]) -> str:
    """Render one line per check (level on 6 columns, name on 10), then the problem count."""
    lines = [f"{c.level.value:<6}{c.name:<10}{c.text}".rstrip() for c in checks]
    problems = sum(c.level in (CheckLevel.WARN, CheckLevel.FAIL) for c in checks)
    if problems:
        lines.append(f"{problems} problem{'' if problems == 1 else 's'} found")
    return "\n".join(lines)


def exit_code(checks: Sequence[Check]) -> int:
    """Return 1 when at least one check failed, else 0."""
    return int(any(c.level is CheckLevel.FAIL for c in checks))
