"""`L` pastes `Work on task #N.` and the session's context carries the task line."""

import time
from pathlib import Path

from meute.cli.context import CliContext
from meute.cli.task_launch import launch_on_task
from meute.cli.tmux_env import TmuxEnv
from meute.core.instants import format_instant
from support import FIXED, load_json
from test_board_backend import env  # noqa: F401 — fixture reused  # pyright: ignore[reportUnusedImport] — fixture reused
from test_task_launch import (
    _END,  # pyright: ignore[reportPrivateUsage] — helper reused
    _ENVIRON,  # pyright: ignore[reportPrivateUsage] — helper reused
    _START,  # pyright: ignore[reportPrivateUsage] — helper reused
    _fake_claude,  # pyright: ignore[reportPrivateUsage] — helper reused
    _pasted,  # pyright: ignore[reportPrivateUsage] — helper reused
    _task_in_repo,  # pyright: ignore[reportPrivateUsage] — helper reused
    ctx,  # noqa: F401 — fixture reused  # pyright: ignore[reportUnusedImport] — fixture reused
)


def test_l_pastes_the_short_line_unsent_and_the_context_names_the_task(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    recorded = _fake_claude(env, tmp_path, "paste")
    for name, value in {
        "HOME": str(tmp_path),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "MEUTE_NOW": format_instant(FIXED),
    }.items():
        _ = env.tmux.run("set-environment", "-g", name, value)
    task = _task_in_repo(ctx, tmp_path, "Fix the bug")
    ready = launch_on_task(ctx, env, task.id, _ENVIRON, monotonic=time.monotonic, sleep=time.sleep)
    assert ready
    assert _pasted(recorded) == f"{_START}Work on task #{task.id}.{_END}".encode()
    args = load_json((tmp_path / "args.json").read_text(encoding="utf-8"))
    assert isinstance(args, list)
    context = args[args.index("--append-system-prompt") + 1]
    assert isinstance(context, str)
    assert f"You are working on task #{task.id}." in context
