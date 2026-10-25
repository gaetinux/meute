"""`CliBoardBackend.perform` saves the board's sessions (`S`) and reopens a saved state (`O`)."""

from pathlib import Path

import pytest

from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import ReopenState, SaveState
from meute.core.db.saved_states import get_state, save_state
from meute.core.db.sessions import list_sessions
from meute.core.errors import ActionNotice, MeuteError
from meute.core.session import SessionId
from meute.core.session_state import is_live
from support import saved_session
from test_board_backend import _ENVIRON, _Clock, env  # noqa: F401 — fixture reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixture reused
from test_board_backend_stop import ctx  # noqa: F401 — fixture reused  # pyright: ignore[reportUnusedImport] — fixture reused

_STAMP = "2026-10-14 08:30"  # FIXED, in the zone of `ctx.now` (UTC)


def test_save_state_saves_the_live_sessions_under_the_local_time(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="shell"), _ENVIRON)
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    _ = backend.load()
    with pytest.raises(ActionNotice) as told:
        backend.perform(SaveState())
    assert str(told.value) == f"state saved: {_STAMP}"
    assert [s.session_id for s in get_state(ctx.db, _STAMP).sessions] == [session.id]
    data = backend.load()
    assert data is not None
    assert _STAMP in [state.name for state in data.saved_states]


def test_save_state_before_any_load_reads_the_board(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="shell"), _ENVIRON)
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    with pytest.raises(ActionNotice):
        backend.perform(SaveState())
    assert [s.session_id for s in get_state(ctx.db, _STAMP).sessions] == [session.id]


def test_reopen_state_reopens_its_sessions_and_tells_the_counts(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    saved = saved_session(SessionId("aaaa1111-0000-4000-8000-000000000000"), cwd=tmp_path)
    gone = saved_session(
        SessionId("bbbb2222-0000-4000-8000-000000000000"), title="gone", cwd=tmp_path / "gone"
    )
    _ = save_state(ctx.db, "morning", (saved, gone))
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    with pytest.raises(ActionNotice) as told:
        backend.perform(ReopenState(name="morning"))
    assert str(told.value) == "reopened 1 · skipped 1"
    live = [s for s in list_sessions(ctx.db) if is_live(s.state)]
    assert [(s.title, s.cwd) for s in live] == [("shell", tmp_path)]


def test_reopen_state_of_an_unknown_name_fails(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
) -> None:
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    with pytest.raises(MeuteError, match="no saved state named ghost"):
        backend.perform(ReopenState(name="ghost"))
