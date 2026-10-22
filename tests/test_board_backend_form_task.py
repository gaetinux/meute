"""`CliBoardBackend.perform(LaunchClaude)` with a task: like `L`, its text pasted once ready."""

from collections.abc import Mapping
from pathlib import Path

import pytest

import meute.cli.board_backend as board_backend_module
from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.session_launch_claude import ClaudeLaunch
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import LaunchClaude
from meute.core.errors import PromptNotPasted
from meute.core.project import RepoId
from meute.core.task import TaskId
from test_board_backend import _ENVIRON, env  # noqa: F401 — fixture reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixture reused
from test_board_backend_launch import ctx  # noqa: F401 — fixture reused  # pyright: ignore[reportUnusedImport] — fixture reused

_ACTION = LaunchClaude(
    cwd=Path("/w/x"), repo_id=RepoId(1), title="Mine", task_id=TaskId(7), permission_mode="plan"
)


class _Launch:
    """Stands for `launch_claude_on_task`: notes what it was given, returns `ready`."""

    def __init__(self, *, ready: bool) -> None:
        self.ready = ready
        self.calls: list[tuple[CliContext, ClaudeLaunch, TaskId]] = []

    def __call__(
        self,
        context: CliContext,
        _env: TmuxEnv,
        request: ClaudeLaunch,
        task_id: TaskId,
        _environ: Mapping[str, str],
        **_: object,
    ) -> bool:
        self.calls.append((context, request, task_id))
        return self.ready


def test_the_form_request_is_launched_on_its_own_connection(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch = _Launch(ready=True)
    monkeypatch.setattr(board_backend_module, "launch_claude_on_task", launch)
    CliBoardBackend(ctx, env, _ENVIRON).perform(_ACTION)
    ((context, request, task_id),) = launch.calls
    assert context.db is not ctx.db
    assert task_id == TaskId(7)
    assert request == ClaudeLaunch(
        cwd=Path("/w/x"),
        title="Mine",
        repo_id=RepoId(1),
        permission_mode="plan",
        task_id=TaskId(7),
    )


def test_claude_not_ready_is_told_as_prompt_not_pasted(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(board_backend_module, "launch_claude_on_task", _Launch(ready=False))
    with pytest.raises(PromptNotPasted) as raised:
        CliBoardBackend(ctx, env, _ENVIRON).perform(_ACTION)
    assert raised.value.task_id == TaskId(7)
