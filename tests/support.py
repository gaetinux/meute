"""Helpers shared by the tests: plain functions, not fixtures."""

import json
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from meute.core.actor import Actor, Author, Channel
from meute.core.board_view import BoardData, SessionRow
from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.task_update import update_task
from meute.core.db.tasks import create_task
from meute.core.instants import parse_zoned
from meute.core.json_types import JsonValue
from meute.core.project import ProjectId, RepoId
from meute.core.repo import Repo
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import Exited, Running
from meute.core.status import Blocked, InProgress, Priority, Review, TaskStatus, Todo
from meute.core.status import Done as DoneStatus
from meute.core.task import Due, DueAt, DueDate, NewTask, Task, TaskId, TaskPatch

NOW = parse_zoned("2026-10-14T10:30[Europe/Paris]")  # a Wednesday


def date_due(text: str) -> DueDate:
    """Build a date-only due from `YYYY-MM-DD`."""
    return DueDate(day=date.fromisoformat(text))


def at_due(zoned: str) -> DueAt:
    """Build a due with a time from `YYYY-MM-DDTHH:MM[Zone]`."""
    return DueAt(at=parse_zoned(zoned))


USER = Actor(author=Author.USER, channel=Channel.CLI)
CLAUDE = Actor(author=Author.CLAUDE, channel=Channel.MCP, session_id="s-1")
FIXED = datetime(2026, 10, 14, 8, 30, tzinfo=UTC)


def new_task(title: str, project_id: ProjectId | None = None) -> NewTask:
    """Build a task creation request with default fields."""
    return NewTask(title=title, project_id=project_id)


def make_task(
    task_id: int,
    *,
    due: Due | None = None,
    status: TaskStatus | None = None,
    priority: Priority = Priority.NORMAL,
    completed_at: datetime | None = None,
) -> Task:
    """Build a task with fixed timestamps and the title `task <id>`."""
    return Task(
        id=TaskId(task_id),
        title=f"task {task_id}",
        description="",
        status=Todo() if status is None else status,
        priority=priority,
        due=due,
        project=None,
        repo_id=None,
        version=1,
        created_at=FIXED,
        updated_at=FIXED,
        completed_at=completed_at,
    )


def load_json(text: str) -> JsonValue:
    """Parse JSON text into plain objects."""
    return json.loads(text)  # pyright: ignore[reportAny] — json.loads is typed as returning Any


def seed_mixed(db: Database) -> None:
    """Create project `meute` and eight tasks covering every status, priority and due kind."""
    project = create_project(db, "meute")
    rows: list[tuple[str, Priority, Due | None, ProjectId | None, TaskStatus]] = [
        ("Tidy the desk", Priority.NORMAL, None, None, Todo()),
        ("Write the guide", Priority.HIGH, date_due("2026-10-15"), project.id, InProgress()),
        (
            "Deploy",
            Priority.URGENT,
            date_due("2026-10-14"),
            project.id,
            Blocked(reason="waiting for CI"),
        ),
        ("Review the PR", Priority.NORMAL, date_due("2026-10-12"), None, Review()),
        ("Close the ticket", Priority.LOW, None, project.id, DoneStatus()),
        ("Prepare the demo", Priority.NORMAL, date_due("2026-10-21"), project.id, Todo()),
        ("Call Marie", Priority.HIGH, at_due("2026-10-14T15:00[Europe/Paris]"), None, Todo()),
        ("Pay the invoice", Priority.NORMAL, date_due("2026-10-10"), None, Todo()),
    ]
    for title, priority, due, project_id, status in rows:
        task = create_task(
            db,
            NewTask(title=title, priority=priority, due=due, project_id=project_id),
            USER,
        )
        if not isinstance(status, Todo):
            update_task(db, task.id, 1, TaskPatch(status=status), USER)


def wait_until(what: str, predicate: Callable[[], bool], *, timeout: float = 10.0) -> None:
    """Poll `predicate` every 100 ms until it holds, or fail after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            msg = f"timed out waiting for {what}"
            raise AssertionError(msg)
        time.sleep(0.1)


def status_within_grace(read: Callable[[], int | None], *, grace: float = 2.0) -> int | None:
    """Poll `read` for up to `grace` seconds; None means the status never showed up.

    tmux 3.4 may lose the exit status of a dead pane for good (no status, no signal), and any
    tmux briefly shows a dead pane before its status is recorded.
    """
    deadline = time.monotonic() + grace
    status = read()
    while status is None and time.monotonic() < deadline:
        time.sleep(0.1)
        status = read()
    return status


BOARD_AT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
BOARD_HOME = Path("/home/me")
BOARD_ID_A = SessionId("11111111-1111-4111-8111-111111111111")
BOARD_ID_B = SessionId("22222222-2222-4222-8222-222222222222")


def board_session(
    session_id: SessionId, title: str, cwd: Path, repo_id: RepoId | None, *, exited: bool
) -> Session:
    """Build a Bash session for the board tests, running or exited with code 2."""
    return Session(
        id=session_id,
        agent=AgentKind.BASH,
        title=title,
        project_id=None,
        repo_id=repo_id,
        task_id=None,
        cwd=cwd,
        state=Exited(code=2) if exited else Running(),
        last_activity_at=BOARD_AT,
        created_at=BOARD_AT,
        ended_at=None,
    )


def board_repo(repo_id: int, name: str, kind: str | None) -> Repo:
    """Build a repository under `~/git` for the board tests."""
    return Repo(
        id=RepoId(repo_id),
        path=BOARD_HOME / "git" / name,
        name=name,
        kind=kind,
        discovered_at=BOARD_AT,
    )


BOARD_SESSION_A = board_session(
    BOARD_ID_A, "build", BOARD_HOME / "git" / "meute", RepoId(1), exited=False
)
BOARD_SESSION_B = board_session(BOARD_ID_B, "tests", Path("/srv/work"), None, exited=True)
BOARD_REPO_1 = board_repo(1, "meute", "rust")
BOARD_REPO_2 = board_repo(2, "notes", None)


def board_data() -> BoardData:
    """Return two sessions (the first displayed), two repositories and one orphan pane."""
    return BoardData(
        sessions=(
            SessionRow(session=BOARD_SESSION_A, has_pane=True, displayed=True),
            SessionRow(session=BOARD_SESSION_B, has_pane=True, displayed=False),
        ),
        repos=(BOARD_REPO_1, BOARD_REPO_2),
        orphans=("%7",),
        home=BOARD_HOME,
    )
