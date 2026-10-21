"""Orphan panes: panes marked for meute whose `@meute_id` matches no session."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from meute.core.errors import InvalidInput
from meute.core.paths import display_path
from meute.core.repo import Repo
from meute.core.session import AgentKind, NewSession, parse_session_id
from meute.core.session_state import Running, Unknown
from meute.core.text import printable

ORPHAN_KEYS = "orphan pane: Enter show · a adopt · x close"
"""What an orphan pane answers to the keys that act on sessions."""

ORPHAN_FOOTER = "Enter show · a adopt · x close"
"""The footer while an orphan pane is selected."""

_NOT_A_MEUTE_ID = "not a meute id: only x closes it"
_DEAD_PANE = "dead pane: only x closes it"
_UNKNOWN_FOLDER = "unknown folder: only x closes it"
_UNTITLED = "orphan"


@dataclass(frozen=True, slots=True, kw_only=True)
class Orphan:
    """A pane carrying a `@meute_id` unknown to the database, as tmux describes it.

    Every field comes from tmux and may hold anything: show it through `printable`, and
    check `meute_id` before writing it anywhere.
    """

    meute_id: str
    pane_id: str
    command: str
    cwd: str
    dead: bool


def orphan_line(orphan: Orphan, home: Path | None) -> str:
    """Return `? {command}  {folder}  orphan` (`dead` for a dead pane) on one printable line."""
    folder = display_path(Path(orphan.cwd), home) if orphan.cwd else ""
    state = "dead" if orphan.dead else "orphan"
    return f"? {printable(orphan.command)}  {printable(folder)}  {state}"


def confirm_close_text(command: str) -> str:
    """Return the confirmation prompt shown before closing an orphan pane."""
    return f'Close orphan pane "{printable(command)}"? y: yes · any other key: no'


def closing_text(command: str) -> str:
    """Return the footer text while an orphan pane is being closed."""
    return f'Closing "{printable(command)}"…'


def orphan_agent(orphan: Orphan) -> AgentKind:
    """Return what runs in the pane: Claude when the command is `claude`, else Bash."""
    return AgentKind.CLAUDE if orphan.command == "claude" else AgentKind.BASH


def adoption(orphan: Orphan, repos: Sequence[Repo]) -> NewSession | str:
    """Return the session that adopts `orphan`, or the reason it cannot be adopted.

    Nothing reaches the database unless `orphan.meute_id` is a canonical session identifier,
    the pane is alive and its folder is an absolute path. The repository is the known one
    with the longest path that holds the pane's folder.
    """
    try:
        session_id = parse_session_id(orphan.meute_id)
    except InvalidInput:
        return _NOT_A_MEUTE_ID
    if session_id != orphan.meute_id:  # reconcile compares the tag exactly: only a canonical id
        return _NOT_A_MEUTE_ID
    if orphan.dead:
        return _DEAD_PANE
    cwd = Path(orphan.cwd)
    if not cwd.is_absolute():  # tmux may not know it: an empty path would read as `.`
        return _UNKNOWN_FOLDER
    holders = [repo for repo in repos if cwd.is_relative_to(repo.path)]
    repo = max(holders, key=lambda held: len(held.path.parts), default=None)
    agent = orphan_agent(orphan)
    return NewSession(
        id=session_id,
        agent=agent,
        title=cwd.name.strip() or _UNTITLED,
        cwd=cwd,
        state=Unknown() if agent is AgentKind.CLAUDE else Running(),
        repo_id=None if repo is None else repo.id,
    )
