"""`stuck?` depends on silence only, not on `claude agents`."""

import stat
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_launch_claude import ClaudeLaunch, launch_claude
from meute.cli.session_refresh import refresh
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.sessions import set_session_state
from meute.core.session_state import MaybeStuck, Running, SessionState
from test_board_backend import _ENVIRON, _SPEC, ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixtures reused


def _fake_claude(tmp_path: Path) -> dict[str, str]:
    fake = tmp_path / "bin"
    fake.mkdir()
    script = fake / "claude"
    script.write_text("#!/bin/sh\nexec sleep 3600\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return {"PATH": str(fake), "SHELL": "/bin/sh"}


def _states(context: CliContext, tmux_env: TmuxEnv, silence: timedelta) -> list[SessionState]:
    later = replace(context, now=context.now + silence)
    return [row.session.state for row in refresh(later, tmux_env, agents=None).sessions]


def test_silent_running_claude_is_stuck_without_agents(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    session = launch_claude(ctx, env, ClaudeLaunch(cwd=tmp_path), _fake_claude(tmp_path))
    set_session_state(ctx.db, session.id, Running())  # a hook said so; it launches as unknown
    minutes = ctx.config.claude.stuck_after_minutes
    assert _states(ctx, env, timedelta(minutes=minutes - 1)) == [Running()]
    assert _states(ctx, env, timedelta(minutes=minutes + 1)) == [MaybeStuck()]


def test_silent_bash_is_untouched(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    _ = launch_bash(ctx, env, BashLaunch(cwd=tmp_path), _ENVIRON)
    assert _states(ctx, env, timedelta(hours=5)) == [Running()]
