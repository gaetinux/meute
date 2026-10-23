"""A task picked in the launch form (`N`): Claude in the form's folder, the task text pasted."""

import time
from pathlib import Path

from meute.cli.context import CliContext
from meute.cli.session_launch_claude import ClaudeLaunch
from meute.cli.task_launch import launch_claude_on_task
from meute.cli.tmux_env import TmuxEnv
from meute.core.context import work_on_task_text
from meute.core.db.sessions import list_sessions
from meute.tmux.panes import list_panes
from support import load_json
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


def test_the_form_folder_title_and_mode_are_kept_and_the_text_pasted(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    recorded = _fake_claude(env, tmp_path, "paste")
    task = _task_in_repo(ctx, tmp_path, "Fix the bug")
    folder = tmp_path / "elsewhere"
    folder.mkdir()
    request = ClaudeLaunch(cwd=folder, title="Mine", permission_mode="plan")
    ready = launch_claude_on_task(
        ctx, env, request, task.id, _ENVIRON, monotonic=time.monotonic, sleep=time.sleep
    )
    assert ready
    text = work_on_task_text(task.id)
    assert _pasted(recorded) == f"{_START}{text.replace('\n', '\r')}{_END}".encode()
    (session,) = list_sessions(ctx.db)
    assert (session.task_id, session.title, session.cwd) == (task.id, "Mine", folder)
    args = load_json((tmp_path / "args.json").read_text(encoding="utf-8"))
    assert isinstance(args, list)
    assert "--name=Mine" in args
    assert args[args.index("--permission-mode") + 1] == "plan"
    assert any(p.meute_id == session.id for p in list_panes(env.tmux))
