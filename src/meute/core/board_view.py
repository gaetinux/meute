"""The dashboard view model: what the board shows and decides, without any UI toolkit."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import assert_never

from meute.core.agents import AgentInfo
from meute.core.claude_session import ClaudeDetails
from meute.core.paths import display_path
from meute.core.project import ProjectId, RepoId
from meute.core.quota_view import QuotaLine
from meute.core.repo import Repo
from meute.core.session import Session, SessionId
from meute.core.session_state import state_label
from meute.core.statusline import StatuslineData
from meute.core.text import printable

BOARD_TITLE = "meute"
SESSIONS_HEADING = "Sessions"
REPOS_HEADING = "Repositories"
ORPHANS_HEADING = "Orphans"
OUTSIDE_HEADING = "Outside meute"
NO_SESSIONS = "No sessions. Pick a repository and press n."
FOOTER = "↑↓ select · Enter show · c Claude · n Bash · x stop · a attention · e ended · q detach"

_DISPLAYED_MARK = "▶ "
_NOT_DISPLAYED_MARK = "  "


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionRow:
    """A session with what tmux says about it."""

    session: Session
    has_pane: bool
    displayed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class BoardData:
    """Everything the board draws; `now` is the clock the ages are measured by.

    `sessions` are the live sessions and those that still have a pane; `ended` are the
    other sessions that ended recently, shown only on demand.
    """

    sessions: tuple[SessionRow, ...]
    repos: tuple[Repo, ...]
    orphans: tuple[str, ...]
    home: Path | None
    outside: tuple[AgentInfo, ...] = ()
    ended: tuple[SessionRow, ...] = ()
    details: Mapping[SessionId, ClaudeDetails] = field(
        default_factory=dict[SessionId, ClaudeDetails]
    )
    metrics: Mapping[SessionId, StatuslineData] = field(
        default_factory=dict[SessionId, StatuslineData]
    )
    projects: Mapping[ProjectId, str] = field(default_factory=dict[ProjectId, str])
    quota: QuotaLine | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ShowSession:
    """Bring a session's pane into the main area."""

    session_id: SessionId


@dataclass(frozen=True, slots=True, kw_only=True)
class LaunchBash:
    """Start a Bash session in `cwd`."""

    cwd: Path
    repo_id: RepoId | None


@dataclass(frozen=True, slots=True, kw_only=True)
class LaunchClaude:
    """Start a Claude session in `cwd`."""

    cwd: Path
    repo_id: RepoId | None


@dataclass(frozen=True, slots=True, kw_only=True)
class StopSession:
    """Stop a session."""

    session_id: SessionId


@dataclass(frozen=True, slots=True, kw_only=True)
class Detach:
    """Detach the terminal from meute, stopping nothing."""


BoardAction = ShowSession | LaunchBash | LaunchClaude | StopSession | Detach


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionEntry:
    """A selectable session."""

    row: SessionRow


@dataclass(frozen=True, slots=True, kw_only=True)
class RepoEntry:
    """A selectable repository."""

    repo: Repo


BoardEntry = SessionEntry | RepoEntry


def board_entries(data: BoardData) -> tuple[BoardEntry, ...]:
    """Return the selectable entries: the sessions in the order received, then the repositories."""
    sessions: tuple[BoardEntry, ...] = tuple(SessionEntry(row=row) for row in data.sessions)
    repos: tuple[BoardEntry, ...] = tuple(RepoEntry(repo=repo) for repo in data.repos)
    return sessions + repos


def entry_key(entry: BoardEntry) -> str:
    """Return a key that identifies `entry` across data refreshes, to keep the selection."""
    match entry:
        case SessionEntry():
            return f"session:{entry.row.session.id}"
        case RepoEntry():
            return f"repo:{entry.repo.id}"
        case _:
            assert_never(entry)


def enter_action(entry: BoardEntry) -> ShowSession | LaunchBash:
    """Return what Enter does: show a session, or launch Bash in a repository."""
    match entry:
        case SessionEntry():
            return ShowSession(session_id=entry.row.session.id)
        case RepoEntry():
            return LaunchBash(cwd=entry.repo.path, repo_id=entry.repo.id)
        case _:
            assert_never(entry)


def new_action(entry: BoardEntry) -> LaunchBash:
    """Return what `n` does: launch Bash in the repository, or where the session runs."""
    match entry:
        case SessionEntry():
            session = entry.row.session
            return LaunchBash(cwd=session.cwd, repo_id=session.repo_id)
        case RepoEntry():
            return LaunchBash(cwd=entry.repo.path, repo_id=entry.repo.id)
        case _:
            assert_never(entry)


def claude_action(entry: BoardEntry) -> LaunchClaude:
    """Return what `c` does: launch Claude where `n` would launch Bash."""
    launch = new_action(entry)
    return LaunchClaude(cwd=launch.cwd, repo_id=launch.repo_id)


def stop_target(entry: BoardEntry) -> Session | None:
    """Return the session `x` would stop; a repository has none."""
    match entry:
        case SessionEntry():
            return entry.row.session
        case RepoEntry():
            return None
        case _:
            assert_never(entry)


def session_line(row: SessionRow, home: Path | None) -> str:
    """Return the board line of a session; a leading mark shows the displayed one."""
    session = row.session
    mark = _DISPLAYED_MARK if row.displayed else _NOT_DISPLAYED_MARK
    return (
        f"{mark}{printable(session.title)}  {state_label(session.state)}  "
        f"{printable(display_path(session.cwd, home))}"
    )


def repo_line(repo: Repo) -> str:
    """Return the board line of a repository: its name and, when known, its kind."""
    name = printable(repo.name)
    return name if repo.kind is None else f"{name} ({printable(repo.kind)})"


def outside_line(agent: AgentInfo, home: Path | None) -> str:
    """Return the board line of a Claude session started outside meute (read-only)."""
    return (
        f"{printable(agent.name)}  {printable(agent.status)}  "
        f"{printable(display_path(Path(agent.cwd), home))}"
    )


def confirm_stop_text(title: str) -> str:
    """Return the confirmation prompt shown before stopping a session."""
    return f'Stop "{printable(title)}"? y: yes · any other key: no'


def stopping_text(title: str) -> str:
    """Return the footer text while a session is being stopped."""
    return f'Stopping "{printable(title)}"…'


def error_text(message: str) -> str:
    """Return the footer text for an error."""
    return f"Error: {printable(message)}"


def board_layout(data: BoardData) -> tuple[list[str], tuple[int, ...]]:
    """Return the board lines and, for each entry of `board_entries`, the index of its line."""
    lines = [BOARD_TITLE, "", SESSIONS_HEADING]
    first_session = len(lines)
    lines += [session_line(row, data.home) for row in data.sessions] or [NO_SESSIONS]
    lines += ["", REPOS_HEADING]
    first_repo = len(lines)
    lines += [repo_line(repo) for repo in data.repos]
    if data.outside:
        lines += ["", OUTSIDE_HEADING, *(outside_line(agent, data.home) for agent in data.outside)]
    if data.orphans:
        lines += ["", ORPHANS_HEADING, *(printable(orphan) for orphan in data.orphans)]
    sessions = range(first_session, first_session + len(data.sessions))
    repos = range(first_repo, first_repo + len(data.repos))
    return lines, (*sessions, *repos)


def board_lines(data: BoardData) -> list[str]:
    """Return the board as text lines: the form the TUI reproduces and the snapshots capture."""
    return board_layout(data)[0]


def entry_line_indexes(data: BoardData) -> tuple[int, ...]:
    """Return, for each entry of `board_entries(data)`, the index of its line in `board_lines`."""
    return board_layout(data)[1]
