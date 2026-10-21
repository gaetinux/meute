"""The dashboard view model: what the board shows and decides, without any UI toolkit."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import assert_never

from meute.core.agents import AgentInfo
from meute.core.board_actions import (
    AddNote,
    AdoptOrphan,
    BoardAction,
    ChangeTask,
    CloseOrphan,
    CreateTask,
    DeleteTask,
    Detach,
    LaunchBash,
    LaunchClaude,
    LaunchOnTask,
    MoveToRepoProject,
    OrphanAction,
    ResumeSession,
    ShowPane,
    ShowSession,
    StopSession,
    TaskAction,
)
from meute.core.board_entries import (
    BoardEntry,
    LaunchEntry,
    OrphanEntry,
    RepoEntry,
    SessionEntry,
    SessionRow,
)
from meute.core.claude_session import ClaudeDetails
from meute.core.last_agent import last_agent
from meute.core.orphans import Orphan
from meute.core.paths import display_path
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.quota_view import QuotaLine
from meute.core.repo import Repo
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import is_live
from meute.core.statusline import StatuslineData
from meute.core.task import Note, Task, TaskId, task_label
from meute.core.text import printable

# The actions live in `board_actions` and the entries in `board_entries`; both stay importable
# from here.
__all__ = [
    "AddNote",
    "AdoptOrphan",
    "BoardAction",
    "BoardEntry",
    "ChangeTask",
    "CloseOrphan",
    "CreateTask",
    "DeleteTask",
    "Detach",
    "LaunchBash",
    "LaunchClaude",
    "LaunchEntry",
    "LaunchOnTask",
    "MoveToRepoProject",
    "OrphanAction",
    "OrphanEntry",
    "RepoEntry",
    "ResumeSession",
    "SessionEntry",
    "SessionRow",
    "ShowPane",
    "ShowSession",
    "StopSession",
    "TaskAction",
]

BOARD_TITLE = "meute"
ORPHANS_HEADING = "Orphans"
OUTSIDE_HEADING = "Outside meute"
NO_SESSIONS = "No sessions. Pick a repository and press n."
FOOTER = "↑↓ select · Enter show · c/n new · x stop · ? keys"
KEYS_HELP = (
    "↑↓ select · Enter show · Space ←→ fold a group\n"
    "c new Claude session · x stop\n"
    "r resume an ended Claude session\n"
    "n new (this repository's last type)\n"
    "a attention only · e ended sessions · Tab tasks · q detach\n"
    "? or Esc close this list"
)
TASKS_FOOTER = "a add · s status · d postpone · o note · L Claude · ? keys"
EDIT_FOOTER = "Enter confirm · Esc cancel"
MULTILINE_DESCRIPTION = "multi-line description: edit it with meute task edit"
TASKS_KEYS_HELP = (
    "↑↓ select · Enter show its session · Space ←→ fold · f filter · g group\n"
    "a add · s status · p priority · d postpone · e title · D description\n"
    "@ project · o note · L launch Claude on it · Del delete · Tab sessions\n"
    "? or Esc close this list"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class BoardData:
    """Everything the board draws; `now` is the clock the ages are measured by.

    `sessions` are the live sessions and those that still have a pane; `ended` are the
    other sessions that ended recently, shown only on demand.
    """

    sessions: tuple[SessionRow, ...]
    repos: tuple[Repo, ...]
    orphans: tuple[Orphan, ...]
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
    tasks: tuple[Task, ...] = ()
    notes: Mapping[TaskId, tuple[Note, ...]] = field(default_factory=dict[TaskId, tuple[Note, ...]])
    project_refs: tuple[ProjectRef, ...] = ()
    displayed_project: ProjectRef | None = None
    last_agents: Mapping[RepoId, AgentKind] = field(default_factory=dict[RepoId, AgentKind])


def enter_action(entry: LaunchEntry) -> ShowSession | LaunchBash:
    """Return what Enter does: show a session, or launch Bash in a repository."""
    match entry:
        case SessionEntry():
            return ShowSession(session_id=entry.row.session.id)
        case RepoEntry():
            return LaunchBash(cwd=entry.repo.path, repo_id=entry.repo.id)
        case _:
            assert_never(entry)


def _launch_place(entry: LaunchEntry) -> tuple[Path, RepoId | None]:
    """Return the folder and repository a launch from `entry` uses."""
    match entry:
        case SessionEntry():
            session = entry.row.session
            return session.cwd, session.repo_id
        case RepoEntry():
            return entry.repo.path, entry.repo.id
        case _:
            assert_never(entry)


def new_action(entry: LaunchEntry, data: BoardData) -> LaunchBash | LaunchClaude:
    """Return what `n` does: launch the repository's last session type where `entry` is."""
    cwd, repo_id = _launch_place(entry)
    own = entry.row.session.agent if isinstance(entry, SessionEntry) else None
    if last_agent(data, repo_id, own) is AgentKind.BASH:
        return LaunchBash(cwd=cwd, repo_id=repo_id)
    return LaunchClaude(cwd=cwd, repo_id=repo_id)


def claude_action(entry: LaunchEntry) -> LaunchClaude:
    """Return what `c` does: launch Claude where `n` would launch."""
    cwd, repo_id = _launch_place(entry)
    return LaunchClaude(cwd=cwd, repo_id=repo_id)


def ended_text(title: str, agent: AgentKind = AgentKind.BASH) -> str:
    """Return the footer notice for an ended session that has no pane left to show."""
    name = printable(title)
    match agent:
        case AgentKind.CLAUDE:
            return f'"{name}" has ended: r resumes · c starts a new session'
        case AgentKind.BASH:
            return f'"{name}" has ended: c starts a new Claude session here'
        case _:
            assert_never(agent)


def ended_notice(entry: LaunchEntry) -> str | None:
    """Return what Enter says instead of showing an ended session without a pane, else None.

    An ended session that kept its dead pane still shows: the pane holds its last output.
    """
    match entry:
        case SessionEntry():
            row = entry.row
            if row.has_pane or is_live(row.session.state):
                return None
            return ended_text(row.session.title, row.session.agent)
        case RepoEntry():
            return None
        case _:
            assert_never(entry)


def stop_target(entry: LaunchEntry) -> Session | None:
    """Return the session `x` would stop; a repository has none."""
    match entry:
        case SessionEntry():
            return entry.row.session
        case RepoEntry():
            return None
        case _:
            assert_never(entry)


def resume_target(entry: LaunchEntry, details: Mapping[SessionId, ClaudeDetails]) -> Session | str:
    """Return the session `r` resumes, or the footer text saying why it cannot."""
    match entry:
        case SessionEntry():
            session = entry.row.session
            if session.agent is not AgentKind.CLAUDE:
                return "only Claude sessions resume"
            title = printable(session.title)
            if is_live(session.state):
                return f'"{title}" is still running'
            known = details.get(session.id)
            if known is None or known.native_id is None:
                return f'"{title}" cannot be resumed: Claude never confirmed its id'
            return session
        case RepoEntry():
            return "only Claude sessions resume"
        case _:
            assert_never(entry)


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


def confirm_delete_text(task_id: TaskId, title: str) -> str:
    """Return the confirmation prompt shown before deleting a task."""
    return f'Delete {task_label(task_id)} "{printable(title)}"? y: yes · any other key: no'


def conflict_text(task_id: TaskId) -> str:
    """Return the footer notice when a task changed since it was read."""
    return f"{task_label(task_id)} was modified in the meantime: reloaded"


def stopping_text(title: str) -> str:
    """Return the footer text while a session is being stopped."""
    return f'Stopping "{printable(title)}"…'


def resuming_text(title: str) -> str:
    """Return the footer text while a session is being resumed."""
    return f'Resuming "{printable(title)}"…'


def launching_text(task_id: TaskId) -> str:
    """Return the footer text while Claude is being launched on a task."""
    return f"Launching Claude on {task_label(task_id)}…"


def error_text(message: str) -> str:
    """Return the footer text for an error."""
    return f"Error: {printable(message)}"
