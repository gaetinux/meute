"""The CLI backend of the MCP tools, on a throw-away database."""

from collections.abc import Generator
from dataclasses import replace
from datetime import UTC
from pathlib import Path

import pytest

from meute.cli.mcp_backend import CliMcpBackend, caller_session
from meute.core.actor import Actor, Author, Channel
from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.repos import sync_repos
from meute.core.db.sessions import create_session
from meute.core.db.task_notes import notes
from meute.core.db.tasks import create_task, get_task, history
from meute.core.errors import InvalidInput, NotFound, VersionConflict
from meute.core.json_types import JsonValue
from meute.core.paths import Paths
from meute.core.repo import NewRepo
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from meute.core.task import KEEP, NewTask, TaskId
from meute.mcp.backend import TaskChanges
from support import FIXED

SESSION = SessionId("0b9c1f0e-5f6a-4a43-9d57-5a3f0a1f7c11")
ACTOR = Actor(author=Author.CLAUDE, channel=Channel.MCP, session_id=SESSION)
KEPT = TaskChanges(title=KEEP, description=KEEP, priority=KEEP, due=KEEP, project=KEEP)


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    return Paths.from_roots(
        config_home=tmp_path / "c", data_home=tmp_path / "d", state_home=tmp_path / "s"
    )


@pytest.fixture
def seeded(paths: Paths) -> Generator[Database]:
    with Database.open(paths.db_file, busy_timeout_ms=1000, clock=lambda: FIXED) as db:
        yield db


def backend(paths: Paths, caller: SessionId | None = SESSION) -> CliMcpBackend:
    return CliMcpBackend(paths, caller, lambda: FIXED, UTC)


def add_session(db: Database, **links: object) -> None:
    create_session(
        db,
        NewSession(
            id=SESSION,
            agent=AgentKind.CLAUDE,
            title="s",
            cwd=Path("/w"),
            state=Running(),
            **links,  # pyright: ignore[reportArgumentType] — test helper
        ),
    )


def titles(
    b: CliMcpBackend,
    *,
    project: str | None = None,
    status: str | None = None,
    due: str | None = None,
    include_done: bool = False,
) -> list[JsonValue]:
    listed = b.task_list(project, status, due, include_done=include_done)
    assert isinstance(listed, list)
    return [t["title"] for t in listed if isinstance(t, dict)]


def test_task_read_gives_the_task_and_its_notes(paths: Paths, seeded: Database) -> None:
    task = create_task(seeded, NewTask(title="A"), ACTOR)
    answer = backend(paths).task_read(task.id)
    assert answer["title"] == "A"
    assert answer["version"] == 1
    assert answer["notes"] == []


def test_task_read_of_an_absent_task_is_not_found(paths: Paths) -> None:
    with pytest.raises(NotFound):
        backend(paths).task_read(99)


def test_task_create_records_claude_through_mcp_with_the_session(
    paths: Paths, seeded: Database
) -> None:
    add_session(seeded)
    answer = backend(paths).task_create("Fix", "details", "high", "2026-11-01", None)
    assert answer == {"id": 1, "version": 1}
    task = get_task(seeded, TaskId(1))
    assert (task.description, task.priority.value) == ("details", "high")
    [created] = history(seeded, TaskId(1))
    assert (created.author.value, created.channel.value, created.session_id) == (
        "claude",
        "mcp",
        SESSION,
    )


def test_task_create_without_project_takes_the_project_of_the_session(
    paths: Paths, seeded: Database
) -> None:
    project = create_project(seeded, "web")
    add_session(seeded, project_id=project.id)
    backend(paths).task_create("T", None, None, None, None)
    found = get_task(seeded, TaskId(1)).project
    assert found is not None
    assert found.name == "web"


def test_task_create_takes_the_project_named_like_the_repository(
    paths: Paths, seeded: Database
) -> None:
    create_project(seeded, "Meute")
    [repo] = sync_repos(seeded, [NewRepo(path=Path("/g/meute"), name="meute", kind=None)])
    add_session(seeded, repo_id=repo.id)
    backend(paths).task_create("T", None, None, None, None)
    found = get_task(seeded, TaskId(1)).project
    assert found is not None
    assert found.name == "Meute"


def test_task_create_without_session_or_project_has_none(paths: Paths, seeded: Database) -> None:
    create_project(seeded, "web")
    backend(paths, None).task_create("T", None, None, None, None)
    assert get_task(seeded, TaskId(1)).project is None


def test_task_create_for_a_session_unknown_to_the_database_has_no_project(
    paths: Paths, seeded: Database
) -> None:
    backend(paths).task_create("T", None, None, None, None)
    assert get_task(seeded, TaskId(1)).project is None


def test_task_create_with_an_unknown_project_is_refused(paths: Paths, seeded: Database) -> None:
    with pytest.raises(InvalidInput, match=r"^unknown project: nope$"):
        backend(paths).task_create("T", None, None, None, "nope")
    assert seeded.conn.execute("SELECT COUNT(*) FROM tasks").fetchone() == (0,)


@pytest.mark.parametrize(
    ("priority", "due"), [("huge", None), (None, "tomorrow"), (None, "2026-11-01T10:00")]
)
def test_task_create_refuses_bad_inputs(
    paths: Paths, seeded: Database, priority: str | None, due: str | None
) -> None:
    with pytest.raises(InvalidInput):
        backend(paths).task_create("T", None, priority, due, None)
    assert seeded.conn.execute("SELECT COUNT(*) FROM tasks").fetchone() == (0,)


def test_task_list_filters_by_project_status_due_and_done(paths: Paths, seeded: Database) -> None:
    web = create_project(seeded, "web")
    create_task(seeded, NewTask(title="late", project_id=web.id, due=None), ACTOR)
    b = backend(paths)
    b.task_create("old", None, None, "2026-10-01", "web")
    b.task_create("soon", None, None, "2026-10-16", None)
    b.task_set_status(1, "done", None, 1)
    assert titles(b) == ["old", "soon"]
    assert titles(b, due="overdue") == ["old"]
    assert titles(b, due="week") == ["soon"]
    assert titles(b, project="web") == ["old"]
    assert titles(b, include_done=True) == ["old", "soon", "late"]
    assert titles(b, status="done") == ["late"]


def test_task_list_with_an_unknown_project_or_filter_is_refused(paths: Paths) -> None:
    with pytest.raises(InvalidInput, match="unknown project: x"):
        backend(paths).task_list("x", None, None, include_done=False)
    with pytest.raises(InvalidInput, match="unknown due filter: soon"):
        backend(paths).task_list(None, None, "soon", include_done=False)


def test_task_update_changes_clears_and_keeps(paths: Paths, seeded: Database) -> None:
    create_project(seeded, "web")
    b = backend(paths)
    b.task_create("T", "d", "low", "2026-11-01", "web")
    changes = TaskChanges(title="New", description=KEEP, priority="urgent", due=None, project=None)
    assert b.task_update(1, 1, changes) == {"version": 2}
    task = get_task(seeded, TaskId(1))
    assert (task.title, task.description, task.priority.value) == ("New", "d", "urgent")
    assert (task.due, task.project) == (None, None)
    b.task_update(1, 2, replace(KEPT, project="web", due="2026-12-01"))
    task = get_task(seeded, TaskId(1))
    assert (task.version, task.project is not None, task.due is not None) == (3, True, True)


def test_task_update_refuses_to_clear_the_title_or_priority(paths: Paths) -> None:
    b = backend(paths)
    b.task_create("T", None, None, None, None)
    for field in ("title", "priority"):
        changes = replace(KEPT, **{field: None})
        with pytest.raises(InvalidInput, match=f"{field} cannot be cleared"):
            b.task_update(1, 1, changes)


def test_a_stale_version_changes_nothing(paths: Paths, seeded: Database) -> None:
    b = backend(paths)
    b.task_create("T", None, None, None, None)
    b.task_set_status(1, "review", None, 1)
    with pytest.raises(VersionConflict, match="current version: 2"):
        b.task_update(
            1, 1, TaskChanges(title="X", description=KEEP, priority=KEEP, due=KEEP, project=KEEP)
        )
    with pytest.raises(VersionConflict):
        b.task_set_status(1, "done", None, 1)
    task = get_task(seeded, TaskId(1))
    assert (task.title, task.version) == ("T", 2)


def test_task_set_status_needs_a_reason_for_blocked_only(paths: Paths) -> None:
    b = backend(paths)
    b.task_create("T", None, None, None, None)
    with pytest.raises(InvalidInput, match="blocked needs a reason"):
        b.task_set_status(1, "blocked", None, 1)
    with pytest.raises(InvalidInput, match="a reason only goes with blocked"):
        b.task_set_status(1, "done", "why", 1)
    assert b.task_set_status(1, "blocked", "waiting", 1) == {"version": 2}
    assert b.task_read(1)["blocked_reason"] == "waiting"


def test_task_note_add_records_the_session(paths: Paths, seeded: Database) -> None:
    b = backend(paths)
    b.task_create("T", None, None, None, None)
    assert b.task_note_add(1, " hello ") == {"note_id": 1}
    [note] = notes(seeded, TaskId(1))
    assert (note.body, note.author.value, note.channel.value, note.session_id) == (
        "hello",
        "claude",
        "mcp",
        SESSION,
    )
    with pytest.raises(InvalidInput):
        b.task_note_add(1, "  ")


def test_task_link_session_links_the_calling_session(paths: Paths, seeded: Database) -> None:
    add_session(seeded)
    b = backend(paths)
    b.task_create("T", None, None, None, None)
    assert b.task_link_session(1) == {"session_id": SESSION, "task_id": 1}
    linked = seeded.conn.execute("SELECT task_id FROM sessions WHERE id = ?", (SESSION,))
    assert linked.fetchall() == [(1,)]


@pytest.mark.parametrize("text", [SESSION.upper(), "x;y", "", None])
def test_a_session_variable_that_is_not_exact_means_no_session(
    paths: Paths, seeded: Database, text: str | None
) -> None:
    add_session(seeded)
    caller = caller_session({} if text is None else {"MEUTE_SESSION": text})
    assert caller is None
    b = backend(paths, caller)
    b.task_create("T", None, None, None, None)
    b.task_note_add(1, "n")
    assert {e.session_id for e in history(seeded, TaskId(1))} == {None}
    assert {n.session_id for n in notes(seeded, TaskId(1))} == {None}
    with pytest.raises(InvalidInput, match="no calling session"):
        b.task_link_session(1)


def test_an_exact_session_variable_is_kept() -> None:
    assert caller_session({"MEUTE_SESSION": SESSION}) == SESSION


def test_task_link_session_of_an_absent_task_or_session_is_not_found(
    paths: Paths, seeded: Database
) -> None:
    b = backend(paths)
    b.task_create("T", None, None, None, None)
    with pytest.raises(NotFound, match="session"):
        b.task_link_session(1)
    add_session(seeded)
    with pytest.raises(NotFound, match="task"):
        b.task_link_session(9)


def test_task_update_with_a_null_description_clears_it(paths: Paths, seeded: Database) -> None:
    b = backend(paths)
    b.task_create("T", "details", None, None, None)
    b.task_update(1, 1, replace(KEPT, description=None))
    assert get_task(seeded, TaskId(1)).description == ""
