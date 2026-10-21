"""The dashboard's backend: tmux and the database, read and acted upon by the CLI code."""

import time
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING, assert_never

from meute.claude.launch import find_claude
from meute.cli.agents_poller import AgentsPoller
from meute.cli.board_data import load_board_data
from meute.cli.context import ENVIRONMENT_ERRORS, CliContext, open_database
from meute.cli.orphan_actions import adopt_orphan, close_orphan, show_orphan
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_launch_claude import ClaudeLaunch, launch_claude
from meute.cli.session_resume import resume_session
from meute.cli.session_show import show_session
from meute.cli.session_stop import stop_session
from meute.cli.status_publish import publish_status
from meute.cli.task_launch import READY_TIMEOUT_SECONDS, launch_on_task
from meute.cli.task_quick_create import TUI_ACTOR, create_quick_task, move_to_repo_project
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import (
    AddNote,
    AdoptOrphan,
    BoardAction,
    BoardData,
    ChangeTask,
    CloseOrphan,
    CreateTask,
    DeleteTask,
    Detach,
    LaunchBash,
    LaunchClaude,
    LaunchOnTask,
    MoveToRepoProject,
    OrphanAction,
    ResumeSession,
    ShowPane,
    ShowSession,
    StopSession,
)
from meute.core.db.claude_sessions import purge_samples
from meute.core.db.task_notes import add_note
from meute.core.db.task_update import delete_task, update_task
from meute.core.errors import MeuteError, PromptNotPasted
from meute.core.session import SessionId
from meute.core.task import TaskId
from meute.core.views import count_overdue
from meute.tmux.panes import detach_client

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
        data = load_board_data(self._ctx, self._env, self._environ, self._known)
        self._data_version, self._read_at = version, now
        self._publish_status(data)
        return data

    def _publish_status(self, data: BoardData) -> None:
        """Write the tmux status line when its text changed since the last write."""
        title = next((row.session.title for row in data.sessions if row.displayed), None)
        sessions = [row.session for row in data.sessions]
        pct = None if data.quota is None else data.quota.five_hour_pct
        overdue = 0 if data.now is None else count_overdue(data.tasks, data.now)
        self._status = publish_status(
            self._env.tmux, title, sessions, pct, self._status, overdue=overdue
        )

    def close(self) -> None:
        """Stop the background `claude agents` run, if any."""
        self._agents.close()

    def perform(self, action: BoardAction) -> None:
        """Carry out `action`; the next load rereads.

        Raises:
            MeuteError: the action was refused, or tmux or the database failed.
        """
        try:
            with _as_meute_error():
                self._perform(action)
        finally:
            # Reset on exit too: a slow action may end after a load that missed its effect.
            self._read_at = None

    def _perform(self, action: BoardAction) -> None:  # noqa: C901, PLR0912 — one case per board action
        match action:
            case ShowSession():
                show_session(self._ctx, self._env, action.session_id)
            case LaunchBash():
                request = BashLaunch(cwd=action.cwd, repo_id=action.repo_id, title=action.title)
                session = launch_bash(self._ctx, self._env, request, self._environ)
                show_session(self._ctx, self._env, session.id)
            case LaunchClaude():
                claude = ClaudeLaunch(
                    cwd=action.cwd,
                    repo_id=action.repo_id,
                    title=action.title,
                    permission_mode=action.permission_mode,
                    task_id=action.task_id,
                )
                session = launch_claude(self._ctx, self._env, claude, self._environ)
                show_session(self._ctx, self._env, session.id)
            case StopSession():
                self._stop(action.session_id)
            case ResumeSession():
                self._resume(action.session_id)
            case ShowPane() | AdoptOrphan() | CloseOrphan():
                self._perform_orphan(action)
            case Detach():
                detach_client(self._env.tmux)
            # Task writes go as the TUI user, with the version the board last read.
            case CreateTask():
                _ = create_quick_task(self._ctx, action.text, action.project)
            case ChangeTask():
                _ = update_task(
                    self._ctx.db, action.task_id, action.version, action.patch, TUI_ACTOR
                )
            case MoveToRepoProject():
                move_to_repo_project(self._ctx.db, action.task_id, action.version, action.name)
            case AddNote():
                _ = add_note(self._ctx.db, action.task_id, action.body, TUI_ACTOR)
            case DeleteTask():
                delete_task(self._ctx.db, action.task_id, action.version, TUI_ACTOR)
            case LaunchOnTask():
                self._launch_on_task(action.task_id)
            case _:
                assert_never(action)

    def _perform_orphan(self, action: OrphanAction) -> None:
        match action:
            case ShowPane():
                show_orphan(self._env, action.pane_id)
            case AdoptOrphan():  # in a worker: a connection of its own, like a stop
                with open_database(self._ctx.paths, self._ctx.db.clock) as db:
                    _ = adopt_orphan(replace(self._ctx, db=db), action.orphan)
            case CloseOrphan():
                close_orphan(self._env, action.meute_id, action.agent)
            case _:
                assert_never(action)

    def _launch_on_task(self, task_id: TaskId) -> None:
        """Launch Claude on a task on a connection of its own: the board runs this in a worker.

        Raises:
            PromptNotPasted: Claude was launched but not ready in time for the task text.
        """
        with open_database(self._ctx.paths, self._ctx.db.clock) as db:
            ctx = replace(self._ctx, db=db)
            ready = launch_on_task(
                ctx, self._env, task_id, self._environ, monotonic=time.monotonic, sleep=time.sleep
            )
        if not ready:
            raise PromptNotPasted(task_id, timeout_seconds=READY_TIMEOUT_SECONDS)

    def _stop(self, session_id: SessionId) -> None:
        """Stop a session on a connection of its own: the board runs this in a worker thread.

        The main thread's connection is never touched here (sqlite3 connections are not shared).
        """
        with open_database(self._ctx.paths, self._ctx.db.clock) as db:
            _ = stop_session(replace(self._ctx, db=db), self._env, session_id)

    def _resume(self, session_id: SessionId) -> None:
        """Resume a session on a connection of its own: the board runs this in a worker thread."""
        with open_database(self._ctx.paths, self._ctx.db.clock) as db:
            ctx = replace(self._ctx, db=db)
            session = resume_session(ctx, self._env, session_id, self._environ)
            show_session(ctx, self._env, session.id)
