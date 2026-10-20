"""`CliBoardBackend.perform(LaunchOnTask)`: on a connection of its own, its outcome told."""

from collections.abc import Generator, Mapping
from pathlib import Path

import pytest

import meute.cli.board_backend as board_backend_module
from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import BUSY_TIMEOUT_MS, CliContext
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.board_view import LaunchOnTask
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.db.sessions import list_sessions
from meute.core.db.tasks import create_task, get_task
from meute.core.errors import InvalidInput, PromptNotPasted
from meute.core.paths import Paths
from meute.core.task import TaskId
from support import FIXED, USER, new_task
from test_board_backend import _ENVIRON, env  # noqa: F401 — fixture reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixture reused


@pytest.fixture
def ctx(tmp_path: Path) -> Generator[CliContext]:
    paths = Paths.from_env(
        {"XDG_DATA_HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path)}, home=tmp_path
    )
    with Database.open(paths.db_file, busy_timeout_ms=BUSY_TIMEOUT_MS, clock=lambda: FIXED) as db:
        yield CliContext(
            db=db,
            now=FIXED,
            actor=Actor(author=Author.USER, channel=Channel.CLI),
            config=Config(),
            paths=paths,
        )


def test_a_task_without_repository_is_refused(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    task = create_task(ctx.db, new_task("Nowhere"), USER)
    backend = CliBoardBackend(ctx, env, _ENVIRON)
    with pytest.raises(InvalidInput, match=r"^#1 has no repository: "):
        backend.perform(LaunchOnTask(task_id=task.id))
    assert list_sessions(ctx.db, include_ended=True) == []
    assert get_task(ctx.db, task.id) == task  # the task is left as it was


class _Launch:
    """Stands for `launch_on_task`: notes the database it was given, returns `ready`."""

    def __init__(self, *, ready: bool) -> None:
        self.ready = ready
        self.databases: list[Database] = []

    def __call__(
        self,
        ctx: CliContext,
        _env: TmuxEnv,
        _task_id: TaskId,
        _environ: Mapping[str, str],
        **_: object,
    ) -> bool:
        self.databases.append(ctx.db)
        return self.ready


def test_the_launch_runs_on_its_own_connection(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch = _Launch(ready=True)
    monkeypatch.setattr(board_backend_module, "launch_on_task", launch)
    CliBoardBackend(ctx, env, _ENVIRON).perform(LaunchOnTask(task_id=TaskId(1)))
    (db,) = launch.databases
    assert db is not ctx.db


def test_claude_not_ready_is_told_as_prompt_not_pasted(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(board_backend_module, "launch_on_task", _Launch(ready=False))
    with pytest.raises(PromptNotPasted) as raised:
        CliBoardBackend(ctx, env, _ENVIRON).perform(LaunchOnTask(task_id=TaskId(7)))
    assert raised.value.task_id == TaskId(7)
    assert str(raised.value) == "#7: prompt not pasted (Claude not ready after 10 s)"
