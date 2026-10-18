"""Launching a Claude Code session in the background tmux session."""

from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from meute.claude.launch import claude_argv, find_claude
from meute.claude.settings import write_settings
from meute.cli.context import CliContext
from meute.cli.tmux_env import TmuxEnv, meute_command
from meute.core.config_validate import PERMISSION_MODES
from meute.core.db.sessions import create_session
from meute.core.errors import InvalidInput
from meute.core.project import RepoId
from meute.core.session import AgentKind, NewSession, Session, new_session_id
from meute.core.session_state import Unknown
from meute.tmux.errors import TmuxError
from meute.tmux.names import BG_SESSION, ID_OPTION
from meute.tmux.panes import Spawn, kill_pane, spawn_window

CLAUDE_MISSING = (
    "claude not found: Claude sessions are disabled;"
    " Bash sessions remain available with --kind bash"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaudeLaunch:
    """What to start: the folder, an optional title, repository and permission mode."""

    cwd: Path
    title: str | None = None
    repo_id: RepoId | None = None
    permission_mode: str | None = None


def launch_claude(
    ctx: CliContext, env: TmuxEnv, request: ClaudeLaunch, environ: Mapping[str, str]
) -> Session:
    """Start Claude in `meute-bg` with an explicit permission mode and record the session.

    Raises:
        InvalidInput: the folder does not exist, `claude` is missing or the mode is unknown;
            nothing was started and no session was recorded.
        TmuxError: tmux failed.
    """
    cwd = request.cwd.resolve()
    if not cwd.is_dir():
        message = f"folder not found: {request.cwd}"
        raise InvalidInput(message)
    claude = find_claude(environ)
    if claude is None:
        raise InvalidInput(CLAUDE_MISSING)
    session_id = new_session_id()
    title = request.title or cwd.name
    mode = request.permission_mode or ctx.config.claude.permission_mode
    if mode not in PERMISSION_MODES:
        message = f"unknown permission mode: {mode}"
        raise InvalidInput(message)
    settings = write_settings(ctx.paths.state_dir, session_id, meute_command())
    argv = claude_argv(
        claude=claude, settings=settings, session_id=session_id, permission_mode=mode, title=title
    )
    pane = spawn_window(
        env.tmux,
        Spawn(
            session=BG_SESSION,
            cwd=cwd,
            command=argv,
            env=(("MEUTE_SESSION", session_id),),
            pane_options=((ID_OPTION, session_id), ("remain-on-exit", "on")),
        ),
    )
    try:
        return create_session(
            ctx.db,
            NewSession(
                id=session_id,
                agent=AgentKind.CLAUDE,
                title=title,
                cwd=cwd,
                state=Unknown(),
                repo_id=request.repo_id,
                permission_mode=mode,
            ),
        )
    except BaseException:
        with suppress(TmuxError):  # the pane may be gone already: the first error matters
            kill_pane(env.tmux, pane)
        raise
