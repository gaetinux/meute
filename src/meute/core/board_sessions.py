"""The Sessions view of the board: from `BoardData` to view lines and what each line holds."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import assert_never

from meute.core.board_view import NO_SESSIONS, BoardData, BoardEntry, RepoEntry, SessionEntry
from meute.core.session import SessionId
from meute.core.sessions_view import (
    HeaderLine,
    InfoLine,
    RepoLine,
    SessionInfo,
    SessionLine,
    SessionsView,
    ViewLine,
    ViewState,
    build_view,
    group_name,
)
from meute.core.sessions_view_text import mode_text

RISKY_MODES = frozenset({"auto", "bypassPermissions", "dontAsk"})
"""Permission modes in which Claude acts without asking (spec 6.2): shown in orange."""

_NO_ACTIVITY = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class BoardSessions:
    """The board data, the sessions with their group, and the view lines built from them."""

    data: BoardData
    infos: Mapping[SessionId, SessionInfo]
    view: SessionsView
    now: datetime


def board_sessions(data: BoardData, state: ViewState) -> BoardSessions:
    """Build the Sessions view of `data` as the user folded and filtered it.

    Without `data.now`, ages are measured from the latest activity of the sessions. Without
    any session, the view starts with the hint to start one.
    """
    repos = {repo.id: repo for repo in data.repos}
    infos = {
        row.session.id: SessionInfo(
            row=row,
            details=data.details.get(row.session.id),
            metrics=data.metrics.get(row.session.id),
            group=group_name(row.session, projects=data.projects, repos=repos),
        )
        for row in data.sessions
    }
    now = data.now or max(
        (row.session.last_activity_at for row in data.sessions), default=_NO_ACTIVITY
    )
    view = build_view(
        list(infos.values()), data.repos, data.outside, data.orphans, state, now=now, home=data.home
    )
    if not data.sessions:
        view = SessionsView(lines=(InfoLine(NO_SESSIONS), *view.lines))
    return BoardSessions(data=data, infos=infos, view=view, now=now)


def line_at(board: BoardSessions, index: int) -> ViewLine | None:
    """Return line `index` of the view, or None out of range (-1 included)."""
    return board.view.lines[index] if 0 <= index < len(board.view.lines) else None


def line_info(board: BoardSessions, index: int) -> SessionInfo | None:
    """Return the session on line `index`, or None for any other line or out of range."""
    line = line_at(board, index)
    return board.infos.get(line.session_id) if isinstance(line, SessionLine) else None


def line_entry(board: BoardSessions, index: int) -> BoardEntry | None:
    """Return what the keys act on at line `index`: a session, a repository, or None."""
    line = line_at(board, index)
    match line:
        case SessionLine():
            info = board.infos.get(line.session_id)
            return None if info is None else SessionEntry(row=info.row)
        case RepoLine():
            repo = next((r for r in board.data.repos if r.id == line.repo_id), None)
            return None if repo is None else RepoEntry(repo=repo)
        case HeaderLine() | InfoLine() | None:
            return None
        case _:
            assert_never(line)


def line_group(board: BoardSessions, index: int) -> str | None:
    """Return the group that folding acts on at line `index`: a session's, or a header's."""
    line = line_at(board, index)
    if isinstance(line, HeaderLine):
        return line.group
    info = line_info(board, index)
    return None if info is None else info.group


def risky_mode_span(board: BoardSessions, index: int) -> tuple[int, int] | None:
    """Return where a risky permission mode sits in the text of line `index`, if it has one."""
    line, info = line_at(board, index), line_info(board, index)
    mode = None if info is None or info.details is None else info.details.permission_mode
    if line is None or mode is None or mode not in RISKY_MODES:
        return None
    return len(line.text) - len(mode_text(mode)), len(line.text)
