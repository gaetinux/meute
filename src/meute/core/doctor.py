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


def _first_line(output: str) -> str:
    return next(iter(output.splitlines()), "")


def parse_version(output: str) -> tuple[int, ...] | None:
    """Return the first dotted number of the first line of `output`, or None."""
    found = _VERSION.search(_first_line(output))
    return tuple(int(part) for part in found.group().split(".")) if found else None


def shown_version(output: str, prefix: str) -> str:
    """Return the first line of `output` without `prefix`, printable and cut to 40 characters."""
    return printable(_first_line(output).strip().removeprefix(prefix))[:_SHOWN_MAX]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Tool:
    """How the version output of a tool is judged."""

    prefix: str  # removed from the shown version
    missing: str  # why its absence matters
    unreadable: CheckLevel
    rules: tuple[tuple[tuple[int, ...], CheckLevel, str], ...]  # below a version: level, reason


_TMUX = _Tool(
    prefix="tmux ",
    missing=_TMUX_NEED,
    unreadable=CheckLevel.FAIL,
    rules=(
        (_TMUX_MIN, CheckLevel.FAIL, _TMUX_NEED),
        (_TMUX_META_T, CheckLevel.WARN, "M-t needs tmux 3.3 or later"),
    ),
)
_GIT = _Tool(
    prefix="git version ",
    missing=_GIT_NEED,
    unreadable=CheckLevel.FAIL,
    rules=((_GIT_MIN, CheckLevel.FAIL, _GIT_NEED),),
)
_CLAUDE = _Tool(
    prefix="",
    missing="Claude sessions are disabled",
    unreadable=CheckLevel.WARN,
    rules=((_CLAUDE_MIN, CheckLevel.WARN, "meute is tested with claude 2.1.301 or later"),),
)


def _versioned(tool: _Tool, output: str | None, name: str) -> Check:
    """Judge a version output: not found, unreadable, the first rule it falls below, or ok."""
    if output is None:
        return Check(level=CheckLevel.FAIL, name=name, text=f"not found: {tool.missing}")
    version = parse_version(output)
    if version is None:
        text = f"unreadable version: {shown_version(output, '')}"
        return Check(level=tool.unreadable, name=name, text=text)
    shown = shown_version(output, tool.prefix)
    for minimum, level, reason in tool.rules:
        if version < minimum:
            return Check(level=level, name=name, text=f"{shown}: {reason}")
    return Check(level=CheckLevel.OK, name=name, text=shown)


def tmux_check(output: str | None, *, name: str = "tmux") -> Check:
    """Judge the output of `tmux -V` (None: tmux was not found) on the line `name`."""
    return _versioned(_TMUX, output, name)


def git_check(output: str | None) -> Check:
    """Judge the output of `git --version` (None: git was not found)."""
    return _versioned(_GIT, output, "git")


def claude_check(output: str | None) -> Check:
    """Judge the output of `claude --version` (None: claude was not found)."""
    return _versioned(_CLAUDE, output, "claude")


def options_check(help_text: str) -> Check:
    """Check that `claude --help` lists every option meute passes, comparing whole words."""
    listed = set(_OPTION.findall(help_text))
    missing = [option for option in _CLAUDE_OPTIONS if option not in listed]
    if missing:
        text = f"claude --help does not list: {', '.join(missing)}"
        return Check(level=CheckLevel.FAIL, name="options", text=text)
    text = "claude --help lists every option meute uses"
    return Check(level=CheckLevel.OK, name="options", text=text)


def timeout_check(tool: str, *, name: str | None = None) -> Check:
    """Return the failure of the line `name` (default: `tool`): `tool` did not answer in 5 s."""
    text = f"{tool} did not answer within 5 s"
    return Check(level=CheckLevel.FAIL, name=tool if name is None else name, text=text)


def database_check(shown: str, version: int | None, latest: int) -> Check:
    """Compare the schema `version` of the database at `shown` (None: absent) with `latest`."""
    if version is None:
        level, text = CheckLevel.WARN, f"{shown}: created at the first start"
    elif version < latest:
        level, text = CheckLevel.WARN, f"{shown} (schema {version}): migrated at the next start"
    elif version > latest:
        level, text = (
            CheckLevel.FAIL,
            f"{shown} (schema {version}): newer than this meute ({latest})",
        )
    else:
        level, text = CheckLevel.OK, f"{shown} (schema {version})"
    return Check(level=level, name="database", text=text)


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
