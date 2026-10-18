"""The dashboard's backend: tmux and the database, read and acted upon by the CLI code."""

import time
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, assert_never

from meute.claude.launch import find_claude
from meute.cli.agents_poller import AgentsPoller
from meute.cli.context import ENVIRONMENT_ERRORS, CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_launch_claude import ClaudeLaunch, launch_claude
from meute.cli.session_refresh import refresh
from meute.cli.session_show import show_session
from meute.cli.session_stop import stop_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import (
    BoardAction,
    BoardData,
    LaunchBash,
    LaunchClaude,
    ShowSession,
    StopSession,
)
from meute.core.db.claude_sessions import purge_samples
from meute.core.db.repos import list_repos
from meute.core.errors import MeuteError

if TYPE_CHECKING:
    from meute.core.agents import AgentInfo

TMUX_REREAD_SECONDS = 2.0
SAMPLE_RETENTION = timedelta(days=30)


@contextmanager
def _as_meute_error() -> Generator[None]:
    try:
        yield
    except ENVIRONMENT_ERRORS as error:
        raise MeuteError(str(error)) from error


def purge_old_samples(ctx: CliContext) -> int:
    """Delete the metric and quota samples older than 30 days; return how many (§ 13)."""
    return purge_samples(ctx.db, older_than=ctx.now - SAMPLE_RETENTION)


class CliBoardBackend:
    """Rereads when another process wrote the database, after an action, or every 2 s."""

    def __init__(
        self,
        ctx: CliContext,
        env: TmuxEnv,
        environ: Mapping[str, str],
        *,
        monotonic: Callable[[], float] = time.monotonic,
        agents: AgentsPoller | None = None,
    ) -> None:
        self._ctx = ctx
        self._env = env
        self._environ = environ
        self._monotonic = monotonic
        self._data_version: int | None = None
        self._read_at: float | None = None  # None: the next load rereads
        # A bare environment (no PATH) never searches the real one: tests stay clear of claude.
        claude = find_claude(environ) if "PATH" in environ else None
        self._agents = agents or AgentsPoller(claude, monotonic=monotonic)
        self._known: tuple[AgentInfo, ...] | None = None  # last result of `claude agents`

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
        fresh = self._agents.poll()
        if self._agents.failed and fresh is None:
            fresh = ()  # claude agents stopped answering: forget what it said before
        if fresh is not None and fresh != self._known:
            self._known = fresh
            self._read_at = None  # the assumed states and the outside list changed
        if (
            self._read_at is not None
            and version == self._data_version
            and now - self._read_at < TMUX_REREAD_SECONDS
        ):
            return None
        snapshot = refresh(self._ctx, self._env, agents=self._known)
        repos = list_repos(self._ctx.db)
        self._data_version, self._read_at = version, now
        return BoardData(
            sessions=snapshot.sessions,
            repos=tuple(repos),
            orphans=snapshot.orphans,
            home=Path.home(),
            outside=snapshot.outside,
        )

    def close(self) -> None:
        """Stop the background `claude agents` run, if any."""
        self._agents.close()

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
            case LaunchClaude():
                claude = ClaudeLaunch(cwd=action.cwd, repo_id=action.repo_id)
                session = launch_claude(self._ctx, self._env, claude, self._environ)
                show_session(self._ctx, self._env, session.id)
            case StopSession():
                _ = stop_session(self._ctx, self._env, action.session_id)
            case _:
                assert_never(action)
