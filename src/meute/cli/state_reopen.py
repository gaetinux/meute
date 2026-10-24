"""Reopening a saved state: resume its Claude sessions, restart its Bash sessions, show one."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from meute.cli.context import ENVIRONMENT_ERRORS, CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_refresh import refresh
from meute.cli.session_resume import resume_session
from meute.cli.session_show import show_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.claude_sessions import get_claude_details
from meute.core.errors import MeuteError, NotFound
from meute.core.paths import resolved, shown_path
from meute.core.saved_state import SavedSession, SavedState
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import is_live

ALREADY_RUNNING = "already running"
NO_CONVERSATION_ID = "no conversation id"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReopenReport:
    """How many sessions were reopened, and the title and reason of each one skipped."""

    reopened: int
    skipped: tuple[tuple[str, str], ...]


type _Outcome = tuple[SessionId | None, str | None]
"""The session reopened or already running (else None), and the reason it was skipped."""


@dataclass(frozen=True, slots=True, kw_only=True)
class _Live:
    """The live sessions before the reopening: by id, and the Bash ones by resolved folder."""

    ids: frozenset[SessionId]
    bash: Mapping[Path, SessionId]

    @staticmethod
    def of(sessions: list[Session]) -> "_Live":
        live = [session for session in sessions if is_live(session.state)]
        return _Live(
            ids=frozenset(session.id for session in live),
            bash={resolved(s.cwd): s.id for s in live if s.agent is AgentKind.BASH},
        )


def _missing_folder(folder: Path, cwd: Path) -> str | None:
    """Why `cwd`, resolved as `folder`, cannot be reopened; None when it is a folder."""
    if folder.is_dir():
        return None
    return f"folder not found: {shown_path(cwd, Path.home())}"


def _reopen_claude(
    ctx: CliContext, env: TmuxEnv, environ: Mapping[str, str], saved: SavedSession
) -> _Outcome:
    try:
        native_id = get_claude_details(ctx.db, saved.session_id).native_id
    except NotFound:
        native_id = None
    if native_id is None:
        return None, NO_CONVERSATION_ID
    missing = _missing_folder(resolved(saved.cwd), saved.cwd)
    if missing is not None:
        return None, missing
    return resume_session(ctx, env, saved.session_id, environ).id, None


def _reopen_bash(
    ctx: CliContext, env: TmuxEnv, environ: Mapping[str, str], saved: SavedSession, live: _Live
) -> _Outcome:
    folder = resolved(saved.cwd)
    running = live.bash.get(folder)
    if running is not None:
        return running, ALREADY_RUNNING
    missing = _missing_folder(folder, saved.cwd)
    if missing is not None:
        return None, missing
    request = BashLaunch(cwd=saved.cwd, title=saved.title, repo_id=saved.repo_id)
    return launch_bash(ctx, env, request, environ).id, None


def _reopen_one(
    ctx: CliContext, env: TmuxEnv, environ: Mapping[str, str], saved: SavedSession, live: _Live
) -> _Outcome:
    if saved.session_id in live.ids:
        return saved.session_id, ALREADY_RUNNING
    try:
        match saved.agent:
            case AgentKind.CLAUDE:
                return _reopen_claude(ctx, env, environ, saved)
            case AgentKind.BASH:
                return _reopen_bash(ctx, env, environ, saved, live)
            case _:
                assert_never(saved.agent)
    except (MeuteError, *ENVIRONMENT_ERRORS) as failure:
        return None, str(failure)


def reopen_state(
    ctx: CliContext, env: TmuxEnv, environ: Mapping[str, str], state: SavedState
) -> ReopenReport:
    """Reopen the sessions of `state` in their saved order, then show the displayed one.

    A Claude session is resumed with its conversation (`resume_session`); a Bash session gets a
    new shell in its folder, with its title and repository. A session that is already running,
    or that cannot be reopened, is skipped with its reason, and the next ones go on. The session
    marked displayed, reopened or already running, is brought into the main area; failing to
    show it changes nothing in the report. Nothing is ever stopped.

    Raises:
        TmuxError: tmux could not be read before the reopening; nothing was started.
    """
    live = _Live.of([row.session for row in refresh(ctx, env, assume=False).sessions])
    reopened = 0
    skipped: list[tuple[str, str]] = []
    shown: SessionId | None = None
    for saved in state.sessions:
        session_id, reason = _reopen_one(ctx, env, environ, saved, live)
        if reason is None:
            reopened += 1
        else:
            skipped.append((saved.title, reason))
        if saved.displayed:
            shown = session_id
    if shown is not None:
        try:
            show_session(ctx, env, shown)
        except (MeuteError, *ENVIRONMENT_ERRORS):
            pass  # the sessions are open; only bringing one forward failed
    return ReopenReport(reopened=reopened, skipped=tuple(skipped))
