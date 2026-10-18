"""The Sessions view model: groups, attention marks, folding and selection, without any UI."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import assert_never

from meute.core.agents import AgentInfo
from meute.core.attention import needs_attention
from meute.core.board_view import ORPHANS_HEADING, OUTSIDE_HEADING, REPOS_HEADING, outside_line
from meute.core.board_view import repo_line as _board_repo_line
from meute.core.project import ProjectId, RepoId
from meute.core.repo import Repo
from meute.core.session import Session, SessionId
from meute.core.session_state import is_live
from meute.core.sessions_view_text import SessionInfo, details_lines, header_text, session_text
from meute.core.text import printable

__all__ = [
    "HeaderLine",
    "InfoLine",
    "RepoLine",
    "SessionInfo",
    "SessionLine",
    "SessionsView",
    "ViewLine",
    "ViewState",
    "build_view",
    "details_lines",
    "group_name",
    "keep_selection",
    "line_key",
    "selectable",
]

OTHER_GROUP = "Other"
NOTHING_TO_SHOW = "Nothing needs your attention."


@dataclass(frozen=True, slots=True, kw_only=True)
class ViewState:
    """What the user chose to fold, filter and reveal."""

    collapsed: frozenset[str] = frozenset()
    attention_only: bool = False
    show_ended: bool = False


@dataclass(frozen=True, slots=True)
class HeaderLine:
    """The header of a group."""

    group: str
    text: str
    collapsed: bool = False


@dataclass(frozen=True, slots=True)
class SessionLine:
    """A selectable session."""

    session_id: SessionId
    text: str
    attention: bool


@dataclass(frozen=True, slots=True)
class RepoLine:
    """A selectable repository without a live session."""

    repo_id: RepoId
    text: str


@dataclass(frozen=True, slots=True)
class InfoLine:
    """A line that cannot be selected."""

    text: str


ViewLine = HeaderLine | SessionLine | RepoLine | InfoLine


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionsView:
    """The lines of the Sessions view, top to bottom."""

    lines: tuple[ViewLine, ...]


def group_name(
    session: Session, *, projects: Mapping[ProjectId, str], repos: Mapping[RepoId, Repo]
) -> str:
    """Return the group of `session`: its project, else its repository, else `Other`."""
    if session.project_id is not None and session.project_id in projects:
        return projects[session.project_id]
    if session.repo_id is not None and session.repo_id in repos:
        return repos[session.repo_id].name
    return OTHER_GROUP


def _group_order(name: str) -> tuple[bool, str, str]:
    return (name == OTHER_GROUP, name.casefold(), name)


def _group_lines(
    group: str, members: Sequence[SessionInfo], state: ViewState, now: datetime
) -> list[ViewLine]:
    folded = group in state.collapsed
    header = header_text(group, members) + (" (collapsed)" if folded else "")
    lines: list[ViewLine] = [HeaderLine(group=group, text=header, collapsed=folded)]
    if folded:
        return lines
    ended = 0
    for info in members:
        session = info.row.session
        attention = needs_attention(session.state)
        if state.attention_only and not attention:
            continue
        if not is_live(session.state) and not state.show_ended:
            ended += 1
            continue
        text = session_text(info, now=now)
        lines.append(SessionLine(session_id=session.id, text=text, attention=attention))
    if ended and not state.attention_only:
        lines.append(InfoLine(f"{ended} ended (e to show)"))
    return lines


def _bottom_lines(
    infos: Sequence[SessionInfo],
    repos: Sequence[Repo],
    outside: Sequence[AgentInfo],
    orphans: Sequence[str],
    home: Path | None,
) -> list[ViewLine]:
    busy = {i.row.session.repo_id for i in infos if is_live(i.row.session.state)}
    idle_repos = [repo for repo in repos if repo.id not in busy]
    lines: list[ViewLine] = []
    if idle_repos:
        lines += [InfoLine(""), InfoLine(REPOS_HEADING)]
        lines += [
            RepoLine(repo_id=r.id, text=f"{_board_repo_line(r)}  + session") for r in idle_repos
        ]
    if outside:
        lines += [InfoLine(""), InfoLine(OUTSIDE_HEADING)]
        lines += [InfoLine(outside_line(agent, home)) for agent in outside]
    if orphans:
        lines += [InfoLine(""), InfoLine(ORPHANS_HEADING)]
        lines += [InfoLine(printable(orphan)) for orphan in orphans]
    return lines


def build_view(  # noqa: PLR0913 — everything the view draws, plus the clock and home
    infos: Sequence[SessionInfo],
    repos: Sequence[Repo],
    outside: Sequence[AgentInfo],
    orphans: Sequence[str],
    state: ViewState,
    *,
    now: datetime,
    home: Path | None,
) -> SessionsView:
    """Build the lines of the Sessions view from the current data and the user's choices."""
    groups: dict[str, list[SessionInfo]] = {}
    for info in infos:
        groups.setdefault(info.group, []).append(info)
    lines: list[ViewLine] = []
    for group in sorted(groups, key=_group_order):
        members = groups[group]
        if state.attention_only and not any(needs_attention(i.row.session.state) for i in members):
            continue
        lines += _group_lines(group, members, state, now)
    if state.attention_only and not lines:
        lines = [InfoLine(NOTHING_TO_SHOW)]
    lines += _bottom_lines(infos, repos, outside, orphans, home)
    return SessionsView(lines=tuple(lines))


def line_key(line: ViewLine) -> str | None:
    """Return the key that identifies a selectable line across refreshes; None for the others."""
    match line:
        case SessionLine():
            return f"session:{line.session_id}"
        case RepoLine():
            return f"repo:{line.repo_id}"
        case HeaderLine():
            return f"group:{line.group}" if line.collapsed else None
        case InfoLine():
            return None
        case _:
            assert_never(line)


def selectable(view: SessionsView) -> tuple[int, ...]:
    """Return the indexes of the selectable lines: sessions, repositories, collapsed headers."""
    return tuple(i for i, line in enumerate(view.lines) if line_key(line) is not None)


def keep_selection(
    old_key: str | None, view: SessionsView, fallback: int, *, old_group: str | None = None
) -> int:
    """Return the line index to select: the line with `old_key`, else the `fallback`-th choice.

    When the line is gone because its group `old_group` is now collapsed, that group's header
    is selected.

    `fallback` is a position among the selectable lines, clamped to them. Returns -1 when
    nothing can be selected, so the selection never rests on a header or an information line.
    """
    choices = selectable(view)
    if not choices:
        return -1
    for index in choices:
        if old_key is not None and line_key(view.lines[index]) == old_key:
            return index
    if old_group is not None:
        for index in choices:
            if line_key(view.lines[index]) == f"group:{old_group}":
                return index
    return choices[min(max(fallback, 0), len(choices) - 1)]
