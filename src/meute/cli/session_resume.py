"""Resuming an ended Claude session with `claude --resume`."""

import re
from collections.abc import Mapping
from contextlib import suppress

from meute.claude.launch import claude_argv, find_claude
from meute.cli.context import CliContext
from meute.cli.session_context import ClaudeOrigin, prepare_claude
from meute.cli.session_launch import resolve_folder, session_spawn
from meute.cli.session_launch_claude import CLAUDE_MISSING
from meute.cli.tmux_env import TmuxEnv
from meute.core.config_validate import PERMISSION_MODES
from meute.core.db.claude_sessions import get_claude_details
from meute.core.db.sessions import get_session, reopen_session
from meute.core.errors import InvalidInput
from meute.core.resume_texts import NOT_CLAUDE, no_native_id_text, still_running_text
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import is_live
from meute.tmux.errors import TmuxError
from meute.tmux.panes import kill_pane, pane_of_session, respawn_window, spawn_window

_CLAUDE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")  # never an option, never spaces


def resume_session(
    ctx: CliContext, env: TmuxEnv, session_id: SessionId, environ: Mapping[str, str]
) -> Session:
    """Run `claude --resume` for the ended Claude session `session_id`, then reopen it.

    The dead pane of the session is restarted in place; without one, a new window opens in
    `meute-bg`. The session is unknown until Claude's `SessionStart` hook confirms it.

    Raises:
        InvalidInput: not an ended Claude session with a known Claude id, the folder is gone or
            `claude` is missing; nothing was started and nothing was written.
        NotFound: no such session.
        ConfigError: the configuration file has become invalid; nothing was started.
        TmuxError: tmux failed; the database was not written.
    """
    session = get_session(ctx.db, session_id)
    if session.agent is not AgentKind.CLAUDE:
        message = NOT_CLAUDE
        raise InvalidInput(message)
    if is_live(session.state):
        message = still_running_text(session.title)
        raise InvalidInput(message)
    details = get_claude_details(ctx.db, session_id)
    if details.native_id is None or _CLAUDE_ID.fullmatch(details.native_id) is None:
        message = no_native_id_text(session.title)
        raise InvalidInput(message)
    cwd = resolve_folder(session.cwd)
    claude = find_claude(environ)
    if claude is None:
        raise InvalidInput(CLAUDE_MISSING)
    pane = pane_of_session(env.tmux, session_id)
    if pane is not None and not pane.dead:
        message = still_running_text(session.title)  # restarting it would kill a live process
        raise InvalidInput(message)
    known_mode = details.permission_mode
    origin = ClaudeOrigin(
        project_id=session.project_id,
        repo_id=session.repo_id,
        task_id=session.task_id,
        permission_mode=known_mode if known_mode in PERMISSION_MODES else None,
    )
    start = prepare_claude(ctx, session_id, origin)  # the context of the moment, not the first
    argv = claude_argv(
        claude=claude,
        settings=start.settings,
        session_id=SessionId(details.native_id),
        permission_mode=start.permission_mode,
        title=session.title,
        resume=True,
        mcp_config=start.mcp_config,
        context=start.context,
    )
    spawn = session_spawn(session_id, cwd, argv)
    started = (
        spawn_window(env.tmux, spawn) if pane is None else respawn_window(env.tmux, pane.id, spawn)
    )
    try:
        return reopen_session(ctx.db, session_id)
    except BaseException:
        with suppress(TmuxError):  # the pane may be gone already: the first error matters
            kill_pane(env.tmux, started)
        raise
