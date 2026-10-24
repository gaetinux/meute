"""The `last` state: written by the board when its live sessions change, never emptied."""

from collections.abc import Generator
from dataclasses import replace
from pathlib import Path

import pytest

from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.last_state import LastState
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import BoardData
from meute.core.db.connection import Database
from meute.core.db.saved_states import delete_state, get_state, list_states, save_state
from meute.core.saved_state import LAST, SavedSession
from meute.core.session import AgentKind, SessionId
from support import FIXED
from test_board_backend import _ENVIRON, _Clock, ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixtures reused


def _saved(n: int) -> SavedSession:
    return SavedSession(
        session_id=SessionId(f"{n:08d}-0000-4000-8000-000000000000"),
        agent=AgentKind.BASH,
        cwd=Path("/work"),
        native_id=None,
        title=f"shell {n}",
        task_id=None,
        repo_id=None,
        displayed=False,
    )


ONE, TWO, THREE = _saved(1), _saved(2), _saved(3)


@pytest.fixture
def db(tmp_path: Path) -> Generator[Database]:
    with Database.open(tmp_path / "meute.db", busy_timeout_ms=1000, clock=lambda: FIXED) as db:
        yield db


def _last_ids(db: Database) -> list[SessionId]:
    return [session.session_id for session in get_state(db, LAST).sessions]


def _update(db: Database, sessions: tuple[SavedSession, ...]) -> bool:
    """Update `last` from `sessions`, against the states as a board read finds them."""
    return LastState(db).update(sessions, list_states(db))


def test_a_first_list_is_written(db: Database) -> None:
    assert _update(db, (ONE, TWO))
    assert _last_ids(db) == [ONE.session_id, TWO.session_id]


def test_the_same_list_is_not_written_again(db: Database) -> None:
    assert _update(db, (ONE, TWO))
    # Same ids, another title: nothing to write.
    assert not _update(db, (replace(ONE, title="renamed"), TWO))
    assert get_state(db, LAST).sessions[0].title == "shell 1"


def test_an_empty_list_is_never_written(db: Database) -> None:
    assert not _update(db, ())
    assert list_states(db) == ()
    assert _update(db, (ONE,))
    assert not _update(db, ())
    assert _last_ids(db) == [ONE.session_id]


def test_a_board_that_restarts_with_no_live_session_keeps_last(db: Database) -> None:
    _ = save_state(db, LAST, (ONE, TWO, THREE))
    assert not _update(db, ())
    assert _last_ids(db) == [ONE.session_id, TWO.session_id, THREE.session_id]


def test_a_board_that_restarts_with_the_same_sessions_writes_nothing(db: Database) -> None:
    written = save_state(db, LAST, (ONE, TWO))
    assert not _update(db, (ONE, TWO))
    assert get_state(db, LAST) == written


def test_a_changed_order_writes_nothing(db: Database) -> None:
    # A session that asks for attention moves up the board: `last` keeps its order.
    assert _update(db, (ONE, TWO))
    assert not _update(db, (TWO, ONE))
    assert _last_ids(db) == [ONE.session_id, TWO.session_id]


def test_sessions_stopped_one_by_one_keep_the_full_set(db: Database) -> None:
    assert _update(db, (ONE, TWO, THREE))
    assert not _update(db, (ONE, TWO))
    assert not _update(db, (ONE,))
    assert _last_ids(db) == [ONE.session_id, TWO.session_id, THREE.session_id]


def test_a_new_session_writes_the_whole_live_set(db: Database) -> None:
    assert _update(db, (ONE, TWO))
    assert not _update(db, (TWO,))
    assert _update(db, (TWO, replace(THREE, displayed=True)))
    assert get_state(db, LAST).sessions == (TWO, replace(THREE, displayed=True))


def _loaded(backend: CliBoardBackend) -> BoardData:
    data = backend.load()
    assert data is not None
    return data


def test_a_reread_that_sees_a_new_live_session_updates_last(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    clock = _Clock()
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=clock)
    first = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="first"), _ENVIRON)
    data = _loaded(backend)
    assert _last_ids(ctx.db) == [first.id]
    assert [state.name for state in data.saved_states] == [LAST]
    assert [s.session_id for s in data.saved_states[0].sessions] == [first.id]
    second = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="second"), _ENVIRON)
    clock.now += 2.0
    data = _loaded(backend)
    assert sorted(_last_ids(ctx.db)) == sorted([first.id, second.id])
    assert sorted(s.session_id for s in data.saved_states[0].sessions) == sorted(
        [first.id, second.id]
    )


def test_load_brings_the_saved_states(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
) -> None:
    _ = save_state(ctx.db, "morning", (ONE,))
    data = _loaded(CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock()))
    assert [state.name for state in data.saved_states] == ["morning"]


def test_removing_last_makes_the_next_read_write_it_again(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    clock = _Clock()
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=clock)
    shell = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="shell"), _ENVIRON)
    _ = _loaded(backend)
    delete_state(ctx.db, LAST)  # `meute state rm last`
    clock.now += 2.0
    data = _loaded(backend)
    assert _last_ids(ctx.db) == [shell.id]
    assert [state.name for state in data.saved_states] == [LAST]


def test_a_refused_write_of_last_leaves_the_read_as_it_is(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    clock = _Clock()
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=clock)
    shell = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="shell"), _ENVIRON)
    ctx.db.conn.execute(
        "CREATE TRIGGER refuse BEFORE INSERT ON saved_states BEGIN SELECT RAISE(ABORT, 'no'); END"
    )
    data = _loaded(backend)
    assert [row.session.id for row in data.sessions] == [shell.id]
    assert data.saved_states == ()
    ctx.db.conn.execute("DROP TRIGGER refuse")
    clock.now += 2.0
    _ = _loaded(backend)  # the next read tries again
    assert _last_ids(ctx.db) == [shell.id]
