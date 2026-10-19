"""`CliBoardBackend.perform(StopSession)` runs off the main thread, on its own connection."""

import threading
from collections.abc import Generator
from pathlib import Path

import pytest

from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import BUSY_TIMEOUT_MS, CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.board_view import StopSession
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.db.sessions import get_session
from meute.core.errors import MeuteError
from meute.core.paths import Paths
from meute.core.session import SessionId
from meute.core.session_state import Exited
from support import FIXED
from test_board_backend import _ENVIRON, _Clock, env  # noqa: F401 — fixture reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixture reused


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


def _perform_in_thread(backend: CliBoardBackend, session_id: SessionId) -> BaseException | None:
    failure: list[BaseException] = []

    def work() -> None:
        try:
            backend.perform(StopSession(session_id=session_id))
        except BaseException as error:  # noqa: BLE001 — handed back to the test thread
            failure.append(error)

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    return failure[0] if failure else None


def test_stop_from_another_thread_uses_its_own_connection(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="trial"), _ENVIRON)
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    assert _perform_in_thread(backend, session.id) is None
    # The main thread's connection sees the row the worker's connection wrote.
    assert isinstance(get_session(ctx.db, session.id).state, Exited)
    assert backend.load() is not None  # the stop forced a reread


def test_stop_failure_from_a_thread_is_a_meute_error(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
) -> None:
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    error = _perform_in_thread(backend, SessionId("0" * 32))
    assert isinstance(error, MeuteError)
