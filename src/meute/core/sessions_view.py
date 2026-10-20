"""The Sessions view model: cards, "Needs you", groups, folding and selection, without any UI."""

from collections.abc import Mapping
from dataclasses import replace
from typing import assert_never

from meute.core.project import ProjectId, RepoId
from meute.core.repo import Repo
from meute.core.session import Session, SessionId
from meute.core.sessions_view_cards import (
    OTHER_GROUP,
    REPOS_FOLDED_ABOVE,
    CardLine,
    HeaderLine,
    InfoLine,
    RefLine,
    RepoLine,
    SectionLine,
    SessionLine,
    SessionsView,
    ViewLine,
    ViewState,
    build_view,
    section_key,
)
from meute.core.sessions_view_text import SessionInfo, attention_reason, details_lines

__all__ = [
    "REPOS_FOLDED_ABOVE",
    "CardLine",
    "HeaderLine",
    "InfoLine",
    "RefLine",
    "RepoLine",
    "SectionLine",
    "SessionInfo",
    "SessionLine",
    "SessionsView",
    "ViewLine",
    "ViewState",
    "attention_reason",
    "build_view",
    "details_lines",
    "fold_key",
    "group_name",
    "keep_selection",
    "line_key",
    "section_key",
    "selectable",
    "session_index",
    "with_fold",
]


def with_fold(state: ViewState, key: str, *, fold: bool) -> ViewState:
    """Return `state` with the group or section `key` folded, or unfolded."""
    if fold:
        return replace(state, collapsed=state.collapsed | {key}, expanded=state.expanded - {key})
    return replace(state, collapsed=state.collapsed - {key}, expanded=state.expanded | {key})


def group_name(
    session: Session, *, projects: Mapping[ProjectId, str], repos: Mapping[RepoId, Repo]
) -> str:
    """Return the group of `session`: its project, else its repository, else `Other`."""
    if session.project_id is not None and session.project_id in projects:
        return projects[session.project_id]
    if session.repo_id is not None and session.repo_id in repos:
        return repos[session.repo_id].name
    return OTHER_GROUP


def fold_key(line: ViewLine) -> str | None:
    """Return the key that folds the group or section headed by `line`; None for the others."""
    match line:
        case HeaderLine():
            return line.group
        case SectionLine():
            return section_key(line.section)
        case SessionLine() | CardLine() | RefLine() | RepoLine() | InfoLine():
            return None
        case _:
            assert_never(line)


def line_key(line: ViewLine) -> str | None:
    """Return the key that identifies a selectable line across refreshes; None for the others."""
    match line:
        case SessionLine():
            return f"session:{line.session_id}"
        case RepoLine():
            return f"repo:{line.repo_id}"
        case HeaderLine() | SectionLine():
            return f"group:{fold_key(line)}" if line.collapsed else None
        case CardLine() | RefLine() | InfoLine():
            return None
        case _:
            assert_never(line)


def selectable(view: SessionsView) -> tuple[int, ...]:
    """Return the indexes of the selectable lines: sessions, repositories, folded headings."""
    return tuple(i for i, line in enumerate(view.lines) if line_key(line) is not None)


def session_index(view: SessionsView, session_id: SessionId) -> int:
    """Return the index of the selectable line of session `session_id`, or -1 without one."""
    key = f"session:{session_id}"
    return next((i for i, line in enumerate(view.lines) if line_key(line) == key), -1)


def keep_selection(
    old_key: str | None, view: SessionsView, fallback: int, *, old_group: str | None = None
) -> int:
    """Return the line index to select: the line with `old_key`, else the `fallback`-th choice.

    When the line is gone because its group `old_group` is now collapsed, that group's header
    is selected.

    `fallback` is a position among the selectable lines, clamped to them. Returns -1 when
    nothing can be selected: the selection never rests on an information line, a card's
    other lines, a reference to "Needs you", or an expanded heading (a folded one is
    selectable).
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
