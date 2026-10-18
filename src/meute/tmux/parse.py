"""Parsing of the `tmux -V` output."""

import re
from dataclasses import dataclass
from typing import NewType

from meute.tmux.errors import UnreadableOutput
from meute.tmux.names import ID_OPTION, ROLE_OPTION

_VERSION = re.compile(r"tmux\s+(?:next-)?(\d+)\.(\d+)")


@dataclass(frozen=True, slots=True, kw_only=True, order=True)
class TmuxVersion:
    """A tmux `major.minor` version (letter suffixes such as `3.5a` are dropped)."""

    major: int
    minor: int


MIN_VERSION = TmuxVersion(major=3, minor=2)


def parse_version(output: str) -> TmuxVersion | None:
    """Read `<digits>.<digits>` after `tmux ` or `tmux next-`; None if unreadable."""
    found = _VERSION.match(output.strip())
    if found is None:
        return None
    return TmuxVersion(major=int(found.group(1)), minor=int(found.group(2)))


PaneId = NewType("PaneId", str)  # a tmux pane identifier such as "%12"

PANE_FORMAT = (
    f"#{{pane_id}}\t#{{session_name}}\t#{{window_name}}\t#{{{ID_OPTION}}}\t#{{{ROLE_OPTION}}}"
    "\t#{pane_dead}\t#{pane_dead_status}\t#{pane_width}"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PaneInfo:
    """A pane as reported by `list-panes -F PANE_FORMAT`; empty options are None."""

    id: PaneId
    session: str
    window: str
    meute_id: str | None
    role: str | None
    dead: bool
    dead_status: int | None
    width: int


def _int_field(text: str, what: str, line: str) -> int:
    try:
        return int(text)
    except ValueError:
        msg = f"{what} in pane line {line!r}"
        raise UnreadableOutput(msg) from None


def parse_pane_line(line: str) -> PaneInfo:
    """Parse one `list-panes` line of `PANE_FORMAT`.

    Raises:
        UnreadableOutput: the field count is wrong, or the status or width is not a number.
    """
    fields = line.split("\t")
    if len(fields) != 8:  # noqa: PLR2004 — the eight fields of PANE_FORMAT
        msg = f"expected 8 fields in pane line {line!r}"
        raise UnreadableOutput(msg)
    pane_id, session, window, meute_id, role, dead, dead_status, width = fields
    return PaneInfo(
        id=PaneId(pane_id),
        session=session,
        window=window,
        meute_id=meute_id or None,
        role=role or None,
        dead=dead == "1",
        dead_status=_int_field(dead_status, "exit status", line) if dead_status else None,
        width=_int_field(width, "width", line),
    )
