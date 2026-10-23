"""The actions the board asks its backend to carry out."""

from dataclasses import dataclass
from pathlib import Path

from meute.core.orphans import Orphan
from meute.core.project import ProjectRef, RepoId
from meute.core.session import AgentKind, SessionId
from meute.core.task import TaskId, TaskPatch


@dataclass(frozen=True, slots=True, kw_only=True)
class ShowSession:
    """Bring a session's pane into the main area."""

    session_id: SessionId


@dataclass(frozen=True, slots=True, kw_only=True)
class LaunchBash:
    """Start a Bash session in `cwd`; `title` is the default one when None.

    With `new_branch`, the session starts in a new worktree of `repo_id` on that branch.
    """

    cwd: Path
    repo_id: RepoId | None
    title: str | None = None
    new_branch: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class LaunchClaude:
    """Start a Claude session in `cwd`; None fields take the usual defaults.

    With `new_branch`, the session starts in a new worktree of `repo_id` on that branch.
    """

    cwd: Path
    repo_id: RepoId | None
    title: str | None = None
    task_id: TaskId | None = None
    permission_mode: str | None = None
    new_branch: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StopSession:
    """Stop a session."""

    session_id: SessionId


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumeSession:
    """Resume an ended Claude session with `claude --resume`."""

    session_id: SessionId


@dataclass(frozen=True, slots=True, kw_only=True)
class ShowPane:
    """Bring an orphan pane into the main area."""

    pane_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AdoptOrphan:
    """Record an orphan pane as a session."""

    orphan: Orphan


@dataclass(frozen=True, slots=True, kw_only=True)
class CloseOrphan:
    """Close the orphan pane tagged `meute_id`; `agent` tells how many Ctrl-C it takes."""

    meute_id: str
    agent: AgentKind


@dataclass(frozen=True, slots=True, kw_only=True)
class Detach:
    """Detach the terminal from meute, stopping nothing."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateTask:
    """Create a task from a quick entry; `project` is the default when it has no `@`."""

    text: str
    project: ProjectRef | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeTask:
    """Apply `patch` to a task still at `version`."""

    task_id: TaskId
    version: int
    patch: TaskPatch


@dataclass(frozen=True, slots=True, kw_only=True)
class AddNote:
    """Attach a note to a task."""

    task_id: TaskId
    body: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteTask:
    """Delete a task still at `version`."""

    task_id: TaskId
    version: int


@dataclass(frozen=True, slots=True, kw_only=True)
class LaunchOnTask:
    """Start a Claude session on a task."""

    task_id: TaskId


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveToRepoProject:
    """Move a task still at `version` to the project to create from the repository `name`."""

    task_id: TaskId
    version: int
    name: str


TaskAction = CreateTask | ChangeTask | MoveToRepoProject | AddNote | DeleteTask | LaunchOnTask
OrphanAction = ShowPane | AdoptOrphan | CloseOrphan
BoardAction = (
    ShowSession
    | LaunchBash
    | LaunchClaude
    | StopSession
    | ResumeSession
    | OrphanAction
    | Detach
    | TaskAction
)
