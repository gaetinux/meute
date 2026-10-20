"""Task actions and task data of the board backend, on an in-memory-like temporary database."""

from collections.abc import Generator
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_show import show_session
from meute.cli.task_quick_create import create_quick_task
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.board_view import (
    AddNote,
    BoardData,
    ChangeTask,
    CreateTask,
    DeleteTask,
)
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.repos import sync_repos
from meute.core.db.task_notes import add_note, notes
from meute.core.db.task_update import update_task
from meute.core.db.tasks import TaskFilter, create_task, get_task, history, list_tasks
from meute.core.errors import InvalidInput, MeuteError, VersionConflict
from meute.core.paths import Paths
from meute.core.project import ProjectRef
from meute.core.repo import NewRepo
from meute.core.status import Done, Priority, Review
from meute.core.task import DueDate, NewTask, TaskPatch
from meute.tmux.layout import ensure_layout
from meute.tmux.names import STATUS_OPTION
from support import FIXED, USER, date_due, new_task
from test_board_backend import _ENVIRON, _Clock, env  # noqa: F401 — fixture reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixture reused
from test_board_backend_status import _SPEC  # pyright: ignore[reportPrivateUsage] — layout reused

_TUI = Actor(author=Author.USER, channel=Channel.TUI)


@pytest.fixture
def ctx(tmp_path: Path) -> Generator[CliContext]:
    with Database.open(tmp_path / "meute.db", busy_timeout_ms=1000, clock=lambda: FIXED) as db:
        yield CliContext(
            db=db,
            now=FIXED,
            actor=Actor(author=Author.USER, channel=Channel.CLI),
            config=Config(),
            paths=Paths.from_env({"XDG_STATE_HOME": str(tmp_path)}, home=tmp_path),
        )


def _backend(ctx: CliContext, env: TmuxEnv) -> CliBoardBackend:  # noqa: F811 — fixture
    return CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())


def _loaded(backend: CliBoardBackend) -> BoardData:
    data = backend.load()
    assert data is not None
    return data


def test_create_with_project_priority_and_due(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    project = create_project(ctx.db, "meute")
    _backend(ctx, env).perform(CreateTask(text="Review @Meute !! >2026-10-20", project=None))
    (task,) = list_tasks(ctx.db, TaskFilter())
    assert (task.title, task.priority, task.due) == (
        "Review",
        Priority.URGENT,
        DueDate(day=FIXED.date().replace(day=20)),
    )
    assert task.project == ProjectRef(id=project.id, name="meute")
    assert [e.author for e in history(ctx.db, task.id)] == [Author.USER]
    assert history(ctx.db, task.id)[0].channel is Channel.TUI


def test_create_uses_the_default_project_unless_none(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    project = create_project(ctx.db, "meute")
    default = ProjectRef(id=project.id, name=project.name)
    backend = _backend(ctx, env)
    backend.perform(CreateTask(text="With default", project=default))
    backend.perform(CreateTask(text="Floating @NONE", project=default))
    backend.perform(CreateTask(text="Plain", project=None))
    by_title = {t.title: t.project for t in list_tasks(ctx.db, TaskFilter())}
    assert by_title == {"With default": default, "Floating": None, "Plain": None}


def test_unknown_project_is_refused_and_nothing_is_written(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    with pytest.raises(InvalidInput, match=r"^unknown project: nope$"):
        _backend(ctx, env).perform(CreateTask(text="Lost @nope", project=None))
    assert list_tasks(ctx.db, TaskFilter()) == []


def test_empty_text_is_refused(ctx: CliContext) -> None:
    with pytest.raises(InvalidInput):
        create_quick_task(ctx, "  @none ", None)
    assert list_tasks(ctx.db, TaskFilter()) == []


def test_change_uses_the_version_and_the_tui_actor(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    task = create_task(ctx.db, new_task("Old"), USER)
    backend = _backend(ctx, env)
    backend.perform(ChangeTask(task_id=task.id, version=1, patch=TaskPatch(status=Review())))
    assert get_task(ctx.db, task.id).version == 2
    assert history(ctx.db, task.id)[-1].channel is Channel.TUI


def test_stale_change_is_a_version_conflict(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    task = create_task(ctx.db, new_task("Old"), USER)
    backend = _backend(ctx, env)
    backend.perform(ChangeTask(task_id=task.id, version=1, patch=TaskPatch(title="New")))
    with pytest.raises(VersionConflict):
        backend.perform(ChangeTask(task_id=task.id, version=1, patch=TaskPatch(title="Again")))
    assert get_task(ctx.db, task.id).title == "New"


def test_delete_and_stale_delete(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    task = create_task(ctx.db, new_task("Old"), USER)
    backend = _backend(ctx, env)
    with pytest.raises(VersionConflict):
        backend.perform(DeleteTask(task_id=task.id, version=5))
    backend.perform(DeleteTask(task_id=task.id, version=1))
    assert list_tasks(ctx.db, TaskFilter()) == []
    assert history(ctx.db, task.id)[-1].channel is Channel.TUI


def test_add_note_by_the_tui_user(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    task = create_task(ctx.db, new_task("Old"), USER)
    _backend(ctx, env).perform(AddNote(task_id=task.id, body=" hello "))
    (note,) = notes(ctx.db, task.id)
    assert (note.body, note.author, note.channel) == ("hello", Author.USER, Channel.TUI)


def test_domain_errors_stay_meute_errors(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    with pytest.raises(MeuteError):
        _backend(ctx, env).perform(
            DeleteTask(task_id=create_task(ctx.db, new_task("x"), USER).id, version=9)
        )


def test_load_carries_tasks_notes_and_projects(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    project = create_project(ctx.db, "meute")
    open_task = create_task(ctx.db, new_task("Open", project.id), USER)
    done_old = create_task(ctx.db, new_task("Done today"), USER)
    update_task(ctx.db, done_old.id, 1, TaskPatch(status=Done()), USER)
    add_note(ctx.db, open_task.id, "n1", USER)
    data = _loaded(_backend(ctx, env))
    assert [t.title for t in data.tasks] == ["Open", "Done today"]  # done today is kept
    assert [n.body for n in data.notes[open_task.id]] == ["n1"]
    assert data.project_refs == (ProjectRef(id=project.id, name="meute"),)
    assert data.displayed_project is None


def test_displayed_project_follows_the_repository_name(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    project = create_project(ctx.db, "meute")
    (repo,) = sync_repos(ctx.db, [NewRepo(path=tmp_path, name="Meute", kind=None)])
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, repo_id=repo.id), _ENVIRON)
    _ = ensure_layout(env.tmux, _SPEC)
    show_session(ctx, env, session.id)
    data = _loaded(_backend(ctx, env))
    assert data.displayed_project == ProjectRef(id=project.id, name="meute")


def test_overdue_tasks_are_counted_in_the_status_line(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    _ = ensure_layout(env.tmux, _SPEC)
    for title, day in (("Late", "2026-10-10"), ("Later", "2026-10-13"), ("Fine", "2026-10-30")):
        create_task(ctx.db, NewTask(title=title, due=date_due(day)), USER)
    assert _backend(ctx, env).load() is not None
    assert env.tmux.run("show-options", "-gv", STATUS_OPTION).strip() == "2 overdue"


def test_quick_entry_reads_the_clock_when_the_task_is_created(ctx: CliContext) -> None:
    stale = replace(ctx, now=FIXED - timedelta(days=10))
    task = create_quick_task(stale, "Soon >tomorrow", None)
    assert task.due == DueDate(day=FIXED.date() + timedelta(days=1))


def test_tasks_done_before_today_are_not_loaded(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    old = create_task(ctx.db, new_task("Old"), USER)
    update_task(ctx.db, old.id, 1, TaskPatch(status=Done()), USER)
    with ctx.db.transaction() as conn:
        conn.execute(
            "UPDATE tasks SET completed_at = '2026-10-01T08:30:00.000000Z' WHERE id = ?", (old.id,)
        )
    create_task(ctx.db, new_task("Open"), USER)
    data = _loaded(_backend(ctx, env))
    assert [t.title for t in data.tasks] == ["Open"]
