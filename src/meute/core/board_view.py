"""The dashboard view model: what the board shows and decides, without any UI toolkit."""

from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from meute.core.paths import display_path
from meute.core.project import RepoId
from meute.core.repo import Repo
from meute.core.session import Session, SessionId
from meute.core.session_state import state_label

BOARD_TITLE = "meute"
SESSIONS_HEADING = "Sessions"
REPOS_HEADING = "Repositories"
ORPHANS_HEADING = "Orphans"
NO_SESSIONS = "No sessions. Pick a repository and press n."
FOOTER = "↑↓ select · Enter show · n new Bash · x stop"

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
    """Everything the board draws."""

    sessions: tuple[SessionRow, ...]
    repos: tuple[Repo, ...]
    orphans: tuple[str, ...]
    home: Path | None


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
class StopSession:
    """Stop a session."""

    session_id: SessionId


BoardAction = ShowSession | LaunchBash | StopSession


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
    return f"{mark}{session.title}  {state_label(session.state)}  {display_path(session.cwd, home)}"


def repo_line(repo: Repo) -> str:
    """Return the board line of a repository: its name and, when known, its kind."""
    return repo.name if repo.kind is None else f"{repo.name} ({repo.kind})"


def confirm_stop_text(title: str) -> str:
    """Return the confirmation prompt shown before stopping a session."""
    return f'Stop "{title}"? y: yes · any other key: no'


def error_text(message: str) -> str:
    """Return the footer text for an error."""
    return f"Error: {message}"


def board_layout(data: BoardData) -> tuple[list[str], tuple[int, ...]]:
    """Return the board lines and, for each entry of `board_entries`, the index of its line."""
    lines = [BOARD_TITLE, "", SESSIONS_HEADING]
    first_session = len(lines)
    lines += [session_line(row, data.home) for row in data.sessions] or [NO_SESSIONS]
    lines += ["", REPOS_HEADING]
    first_repo = len(lines)
    lines += [repo_line(repo) for repo in data.repos]
    if data.orphans:
        lines += ["", ORPHANS_HEADING, *data.orphans]
    sessions = range(first_session, first_session + len(data.sessions))
    repos = range(first_repo, first_repo + len(data.repos))
    return lines, (*sessions, *repos)


def board_lines(data: BoardData) -> list[str]:
    """Return the board as text lines: the form the TUI reproduces and the snapshots capture."""
    return board_layout(data)[0]


def entry_line_indexes(data: BoardData) -> tuple[int, ...]:
    """Return, for each entry of `board_entries(data)`, the index of its line in `board_lines`."""
    return board_layout(data)[1]
