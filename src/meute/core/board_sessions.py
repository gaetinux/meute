"""The Sessions view of the board: from `BoardData` to view lines and what each line holds."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import assert_never

from meute.core.board_view import NO_SESSIONS, BoardData, BoardEntry, RepoEntry, SessionEntry
from meute.core.session import SessionId
from meute.core.sessions_view import (
    CardLine,
    HeaderLine,
    InfoLine,
    RefLine,
    RepoLine,
    SectionLine,
    SessionInfo,
    SessionLine,
    SessionsView,
    ViewLine,
    ViewState,
    build_view,
    fold_key,
    group_name,
    section_key,
)
from meute.core.sessions_view_cards import NEEDS_YOU
from meute.core.styled import Span

_NO_ACTIVITY = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class BoardSessions:
    """The board data, the sessions with their group, and the view lines built from them."""

    data: BoardData
    infos: Mapping[SessionId, SessionInfo]
    view: SessionsView
    now: datetime


def board_sessions(data: BoardData, state: ViewState, width: int = 72) -> BoardSessions:
    """Build the Sessions view of `data`, `width` columns wide, as the user folded and filtered it.

    Recently ended sessions without a pane count in their group and show with `show_ended`.
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
        for row in (*data.sessions, *data.ended)
    }
    now = data.now or max(
        (row.session.last_activity_at for row in data.sessions), default=_NO_ACTIVITY
    )
    view = build_view(
        list(infos.values()),
        data.repos,
        data.outside,
        data.orphans,
        state,
        now=now,
        home=data.home,
        width=width,
    )
    if not data.sessions:
        hint = InfoLine(spans=(Span(NO_SESSIONS),))
        rest = (InfoLine(spans=()), *view.lines) if view.lines else ()
        view = SessionsView(lines=(hint, *rest))
    return BoardSessions(data=data, infos=infos, view=view, now=now)


def line_at(board: BoardSessions, index: int) -> ViewLine | None:
    """Return line `index` of the view, or None out of range (-1 included)."""
    return board.view.lines[index] if 0 <= index < len(board.view.lines) else None


def line_info(board: BoardSessions, index: int) -> SessionInfo | None:
    """Return the session of line `index` (a card's lines or a reference to it), else None."""
    line = line_at(board, index)
    match line:
        case SessionLine() | CardLine() | RefLine():
            return board.infos.get(line.session_id)
        case HeaderLine() | SectionLine() | RepoLine() | InfoLine() | None:
            return None
        case _:
            assert_never(line)


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
        case HeaderLine() | SectionLine() | CardLine() | RefLine() | InfoLine() | None:
            return None
        case _:
            assert_never(line)


def line_group(board: BoardSessions, index: int) -> str | None:
    """Return what folding acts on at line `index`: a session's group, or a heading's key."""
    line = line_at(board, index)
    key = None if line is None else fold_key(line)
    if key is not None:
        return key
    if isinstance(line, SessionLine) and line.band:  # a "Needs you" card folds that section
        return section_key(NEEDS_YOU)
    info = line_info(board, index)
    return None if info is None else info.group


def is_folded(board: BoardSessions, key: str) -> bool:
    """Return whether the group or section `key` (see `fold_key`) is folded in the view."""
    return any(
        isinstance(line, HeaderLine | SectionLine) and line.collapsed and fold_key(line) == key
        for line in board.view.lines
    )
