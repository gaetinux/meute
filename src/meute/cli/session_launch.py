"""Launching a Bash session in the background tmux session."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from meute.cli.context import CliContext
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.sessions import create_session
from meute.core.errors import InvalidInput
from meute.core.project import RepoId
from meute.core.session import AgentKind, NewSession, Session, new_session_id
from meute.core.session_state import Running
from meute.tmux.names import BG_SESSION, ID_OPTION
from meute.tmux.panes import Spawn, kill_pane, spawn_window

_DEFAULT_SHELL = "/bin/sh"


@dataclass(frozen=True, slots=True, kw_only=True)
class BashLaunch:
    """What to start: the folder, an optional title and an optional repository."""

    cwd: Path
    title: str | None = None
    repo_id: RepoId | None = None


def launch_bash(
    ctx: CliContext, env: TmuxEnv, request: BashLaunch, environ: Mapping[str, str]
) -> Session:
    """Start the user's shell in `meute-bg` and record the session as running.

    Raises:
        InvalidInput: the folder does not exist; nothing was written or started.
        TmuxError: tmux failed.
    """
    cwd = request.cwd.resolve()
    if not cwd.is_dir():
        message = f"folder not found: {request.cwd}"
        raise InvalidInput(message)
    session_id = new_session_id()
    shell = environ.get("SHELL") or _DEFAULT_SHELL
    pane = spawn_window(
        env.tmux,
        Spawn(
            session=BG_SESSION,
            cwd=cwd,
            command=(shell,),
            env=(("MEUTE_SESSION", session_id),),
            pane_options=((ID_OPTION, session_id), ("remain-on-exit", "on")),
        ),
    )
    try:
        return create_session(
            ctx.db,
            NewSession(
                id=session_id,
                agent=AgentKind.BASH,
                title=request.title or cwd.name,
                cwd=cwd,
                state=Running(),
                repo_id=request.repo_id,
            ),
        )
    except BaseException:
        kill_pane(env.tmux, pane)
        raise
