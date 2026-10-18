"""The dashboard's backend: tmux and the database, read and acted upon by the CLI code."""

import time
from collections.abc import Callable, Collection, Generator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, assert_never

from meute.claude.launch import find_claude
from meute.cli.agents_poller import AgentsPoller
from meute.cli.context import BUSY_TIMEOUT_MS, ENVIRONMENT_ERRORS, CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_launch_claude import ClaudeLaunch, launch_claude
from meute.cli.session_refresh import refresh
from meute.cli.session_show import show_session
from meute.cli.session_stop import stop_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.attention import attention_count
from meute.core.board_view import (
    BoardAction,
    BoardData,
    Detach,
    LaunchBash,
    LaunchClaude,
    SessionRow,
    ShowSession,
    StopSession,
)
from meute.core.clock import local_zone
from meute.core.db.claude_sessions import claude_details_by_session, purge_samples
from meute.core.db.connection import Database
from meute.core.db.projects import list_projects
from meute.core.db.repos import list_repos
from meute.core.db.samples import latest_metrics, latest_quota, quota_history
from meute.core.db.sessions import list_sessions
from meute.core.errors import MeuteError
from meute.core.quota_view import QuotaLine, projected_limit
from meute.core.session import SessionId
from meute.core.session_state import is_live
from meute.core.status_line import status_text
from meute.core.statusline_render import peak_text
from meute.tmux.names import STATUS_OPTION
from meute.tmux.panes import detach_client, set_global_option

if TYPE_CHECKING:
    from meute.core.agents import AgentInfo

TMUX_REREAD_SECONDS = 2.0
SAMPLE_RETENTION = timedelta(days=30)
QUOTA_HISTORY = timedelta(minutes=30)
RECENTLY_ENDED = timedelta(days=7)


@contextmanager
def _as_meute_error() -> Generator[None]:
    try:
        yield
    except ENVIRONMENT_ERRORS as error:
        raise MeuteError(str(error)) from error


def quota_line(ctx: CliContext, now: datetime, environ: Mapping[str, str]) -> QuotaLine:
    """Return the latest quota, its "limit around" projection and the peak hours (spec 7.4)."""
    latest = latest_quota(ctx.db)
    five_resets = None if latest is None else latest.five_hour_resets_at
    history = quota_history(ctx.db, since=now - QUOTA_HISTORY)
    return QuotaLine(
        five_hour_pct=None if latest is None else latest.five_hour_pct,
        five_hour_resets_at=five_resets,
        seven_day_pct=None if latest is None else latest.seven_day_pct,
        seven_day_resets_at=None if latest is None else latest.seven_day_resets_at,
        limit_at=projected_limit(history, resets_at=five_resets, now=now),
        peak=peak_text(now, ctx.config.quotas, local_zone(environ)),
    )


def recently_ended(
    ctx: CliContext, shown: Collection[SessionId], now: datetime
) -> tuple[SessionRow, ...]:
    """Return the sessions ended within 7 days that `shown` lacks: they have no pane."""
    since = now - RECENTLY_ENDED
    return tuple(
        SessionRow(session=session, has_pane=False, displayed=False)
        for session in list_sessions(ctx.db, include_ended=True)
        if not is_live(session.state)
        and session.id not in shown
        and (session.ended_at or session.last_activity_at) >= since
    )


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
        self._status: str | None = None  # last text written to the tmux status line

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
        db = self._ctx.db
        clock = db.now()
        live = [row.session.id for row in snapshot.sessions if is_live(row.session.state)]
        metrics = {session_id: latest_metrics(db, session_id) for session_id in live}
        self._data_version, self._read_at = version, now
        quota = quota_line(self._ctx, clock, self._environ)
        self._publish_status(snapshot.sessions, quota)
        return BoardData(
            sessions=snapshot.sessions,
            repos=tuple(list_repos(db)),
            orphans=snapshot.orphans,
            home=Path.home(),
            outside=snapshot.outside,
            ended=recently_ended(self._ctx, {row.session.id for row in snapshot.sessions}, clock),
            details=claude_details_by_session(db),
            metrics={key: value for key, value in metrics.items() if value is not None},
            projects={project.id: project.name for project in list_projects(db)},
            quota=quota,
            now=clock,
        )

    def _publish_status(self, rows: tuple[SessionRow, ...], quota: QuotaLine) -> None:
        """Write the tmux status line when its text changed since the last write."""
        title = next((row.session.title for row in rows if row.displayed), None)
        attention = attention_count([row.session for row in rows])
        text = status_text(title, attention, quota.five_hour_pct)
        if text != self._status:
            set_global_option(self._env.tmux, STATUS_OPTION, text)
            self._status = text

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
        self._read_at = None  # a slow action may end after a load that missed its effect

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
                self._stop(action.session_id)
            case Detach():
                detach_client(self._env.tmux)
            case _:
                assert_never(action)

    def _stop(self, session_id: SessionId) -> None:
        """Stop a session on a connection of its own: the board runs this in a worker thread.

        The main thread's connection is never touched here (sqlite3 connections are not shared).
        """
        paths = self._ctx.paths
        with Database.open(
            paths.db_file, busy_timeout_ms=BUSY_TIMEOUT_MS, clock=self._ctx.db.clock
        ) as db:
            _ = stop_session(replace(self._ctx, db=db), self._env, session_id)
