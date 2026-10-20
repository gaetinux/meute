"""The board loads only open tasks, tasks done today, and the notes of those tasks."""

from datetime import UTC, datetime

from meute.cli.context import CliContext
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.connection import Database
from meute.core.db.task_notes import add_note
from meute.core.db.task_reads import latest_notes
from meute.core.db.task_update import update_task
from meute.core.db.tasks import TaskFilter, create_task, list_tasks
from meute.core.status import Done
from meute.core.task import TaskId, TaskPatch
from support import USER, new_task
from test_board_backend import env  # noqa: F401 — fixture reused  # pyright: ignore[reportUnusedImport] — fixture reused
from test_board_backend_tasks import _backend, _loaded, ctx  # noqa: F401 — fixture reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — helpers reused

_LONG_AGO = "2026-10-01T08:30:00.000000Z"


def _done(db: Database, title: str, completed_at: str | None = None) -> TaskId:
    task = create_task(db, new_task(title), USER)
    update_task(db, task.id, 1, TaskPatch(status=Done()), USER)
    if completed_at is not None:
        with db.transaction() as conn:
            conn.execute("UPDATE tasks SET completed_at = ? WHERE id = ?", (completed_at, task.id))
    return task.id


def test_done_since_keeps_open_tasks_and_recent_done_ones(db: Database) -> None:
    open_task = create_task(db, new_task("Open"), USER)
    recent = _done(db, "Recent")
    _done(db, "Old", _LONG_AGO)
    since = datetime(2026, 10, 5, tzinfo=UTC)
    found = list_tasks(db, TaskFilter(done_since=since))
    assert [t.id for t in found] == [open_task.id, recent]


def test_latest_notes_of_some_tasks_only(db: Database) -> None:
    first = create_task(db, new_task("one"), USER)
    second = create_task(db, new_task("two"), USER)
    add_note(db, first.id, "a", USER)
    add_note(db, second.id, "b", USER)
    assert set(latest_notes(db, task_ids=[second.id])) == {second.id}
    assert latest_notes(db, task_ids=[]) == {}
    assert set(latest_notes(db)) == {first.id, second.id}


def test_the_board_reads_the_notes_of_the_loaded_tasks_only(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
) -> None:
    open_task = create_task(ctx.db, new_task("Open"), USER)
    today = _done(ctx.db, "Done today")
    old = _done(ctx.db, "Old", _LONG_AGO)
    for task_id in (open_task.id, today, old):
        add_note(ctx.db, task_id, f"note {task_id}", USER)
    data = _loaded(_backend(ctx, env))
    assert [t.title for t in data.tasks] == ["Open", "Done today"]
    assert set(data.notes) == {open_task.id, today}
