"""Two quick jumps (M-n M-n) land on two sessions, not twice on the same one."""

import stat
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from meute.cli import session_jump
from meute.cli.context import CliContext
from meute.cli.session_launch_claude import ClaudeLaunch, launch_claude
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.connection import Database
from meute.core.db.sessions import set_session_state
from meute.core.session import SessionId
from meute.core.session_state import WaitingInput
from meute.tmux.client import Tmux
from meute.tmux.layout import ensure_layout
from meute.tmux.parse import PaneInfo
from test_board_backend import _ENVIRON, _SPEC, ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixtures reused
from test_refresh_stuck import _fake_claude  # pyright: ignore[reportPrivateUsage] — helper reused

# How long the first jump, about to show its session, lets the second one read the screen.
_OVERLAP_SECONDS = 1.0


def _waiting(context: CliContext, tmux_env: TmuxEnv, tmp_path: Path, name: str) -> SessionId:
    folder = tmp_path / name
    folder.mkdir()
    session = launch_claude(context, tmux_env, ClaudeLaunch(cwd=folder), _fake_claude(folder))
    return set_session_state(context.db, session.id, WaitingInput()).id


def _second_jump(
    context: CliContext, tmux_env: TmuxEnv, db_file: Path, errors: list[BaseException]
) -> None:
    try:  # a process of its own would have its own connection
        with Database.open(db_file, busy_timeout_ms=1000, clock=context.db.clock) as db:
            _ = session_jump.jump_to_attention(
                replace(context, db=db), tmux_env, _ENVIRON, backwards=False
            )
    except BaseException as error:  # noqa: BLE001 — reported to the test thread
        errors.append(error)


def test_a_jump_started_during_another_sees_its_result(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ensure_layout(env.tmux, _SPEC)
    waiting = {_waiting(ctx, env, tmp_path, "a"), _waiting(ctx, env, tmp_path, "b")}
    shown: list[SessionId] = []
    errors: list[BaseException] = []
    second_read = threading.Event()
    second = threading.Thread(target=_second_jump, args=(ctx, env, tmp_path / "meute.db", errors))
    real_show = session_jump.show_session
    real_panes = session_jump.main_window_panes

    def panes(tmux: Tmux) -> list[PaneInfo]:
        found = real_panes(tmux)
        if threading.current_thread() is second:  # the second jump reads the screen
            second_read.set()
        return found

    def show(context: CliContext, tmux_env: TmuxEnv, session_id: SessionId) -> None:
        shown.append(session_id)
        if len(shown) == 1:  # the first jump, about to show: the second key press comes now
            second.start()
            _ = second_read.wait(_OVERLAP_SECONDS)
        real_show(context, tmux_env, session_id)

    monkeypatch.setattr(session_jump, "main_window_panes", panes)
    monkeypatch.setattr(session_jump, "show_session", show)
    _ = session_jump.jump_to_attention(ctx, env, _ENVIRON, backwards=False)
    second.join(timeout=30)
    assert errors == []
    assert set(shown) == waiting


def test_an_existing_jump_lock_is_made_private(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
) -> None:
    ensure_layout(env.tmux, _SPEC)
    lock = ctx.paths.state_dir / "jump.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch(mode=0o644)
    lock.chmod(0o644)
    assert session_jump.jump_to_attention(ctx, env, _ENVIRON, backwards=False) is None
    assert stat.S_IMODE(lock.stat().st_mode) == 0o600
