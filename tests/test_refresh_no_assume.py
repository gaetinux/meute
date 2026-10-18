"""Jumps and stops reconcile the panes but leave assumed states to the board (`claude agents`)."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from meute.cli.context import CliContext
from meute.cli.session_jump import jump_to_attention
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_launch_claude import ClaudeLaunch, launch_claude
from meute.cli.session_stop import stop_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.sessions import get_session, set_session_state
from meute.core.session import Session
from meute.core.session_state import Running
from meute.tmux.layout import ensure_layout
from test_board_backend import _ENVIRON, _SPEC, ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixtures reused
from test_refresh_stuck import _fake_claude  # pyright: ignore[reportPrivateUsage] — helper reused


def _silent_busy_claude(context: CliContext, tmux_env: TmuxEnv, tmp_path: Path) -> Session:
    session = launch_claude(context, tmux_env, ClaudeLaunch(cwd=tmp_path), _fake_claude(tmp_path))
    return set_session_state(context.db, session.id, Running())  # `claude agents` says busy


def _later(context: CliContext) -> CliContext:
    silence = timedelta(minutes=context.config.claude.stuck_after_minutes + 1)
    return replace(context, db=replace(context.db, clock=lambda: context.now + silence))


def test_jump_keeps_a_silent_busy_claude_running(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    ensure_layout(env.tmux, _SPEC)
    session = _silent_busy_claude(ctx, env, tmp_path)
    later = _later(ctx)
    assert jump_to_attention(later, env, _ENVIRON, backwards=False) is None
    assert get_session(ctx.db, session.id).state == Running()


def test_stopping_another_session_keeps_a_silent_busy_claude_running(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    session = _silent_busy_claude(ctx, env, tmp_path)
    other = launch_bash(ctx, env, BashLaunch(cwd=tmp_path), _ENVIRON)
    _ = stop_session(_later(ctx), env, other.id, grace=0.2)
    assert get_session(ctx.db, session.id).state == Running()
