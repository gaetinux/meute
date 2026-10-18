"""The dashboard's backend: tmux and the database, read and acted upon by the CLI code."""

import time
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import assert_never

from meute.cli.context import ENVIRONMENT_ERRORS, CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_refresh import refresh
from meute.cli.session_show import show_session
from meute.cli.session_stop import stop_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import BoardAction, BoardData, LaunchBash, ShowSession, StopSession
from meute.core.db.repos import list_repos
from meute.core.errors import MeuteError

TMUX_REREAD_SECONDS = 2.0


@contextmanager
def _as_meute_error() -> Generator[None]:
    try:
        yield
    except ENVIRONMENT_ERRORS as error:
        raise MeuteError(str(error)) from error


class CliBoardBackend:
    """Rereads when another process wrote the database, after an action, or every 2 s."""

    def __init__(
        self,
        ctx: CliContext,
        env: TmuxEnv,
        environ: Mapping[str, str],
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ctx = ctx
        self._env = env
        self._environ = environ
        self._monotonic = monotonic
        self._data_version: int | None = None
        self._read_at: float | None = None  # None: the next load rereads

    def load(self) -> BoardData | None:
        """Return the reconciled data, or `None` when nothing can have changed.

        Raises:
            MeuteError: tmux or the database failed.
        """
        with _as_meute_error():
            return self._load()

    def _load(self) -> BoardData | None:
        now = self._monotonic()
        version = self._ctx.db.data_version()
        if (
            self._read_at is not None
            and version == self._data_version
            and now - self._read_at < TMUX_REREAD_SECONDS
        ):
            return None
        snapshot = refresh(self._ctx, self._env)
        repos = list_repos(self._ctx.db)
        self._data_version, self._read_at = version, now
        return BoardData(
            sessions=snapshot.sessions,
            repos=tuple(repos),
            orphans=snapshot.orphans,
            home=Path.home(),
        )

    def perform(self, action: BoardAction) -> None:
        """Carry out `action`; the next load rereads.

        Raises:
            MeuteError: the action was refused, or tmux or the database failed.
        """
        self._read_at = None
        with _as_meute_error():
            self._perform(action)

    def _perform(self, action: BoardAction) -> None:
        match action:
            case ShowSession():
                show_session(self._ctx, self._env, action.session_id)
            case LaunchBash():
                request = BashLaunch(cwd=action.cwd, repo_id=action.repo_id)
                session = launch_bash(self._ctx, self._env, request, self._environ)
                show_session(self._ctx, self._env, session.id)
            case StopSession():
                _ = stop_session(self._ctx, self._env, action.session_id)
            case _:
                assert_never(action)
