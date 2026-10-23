"""Launching a Claude Code session in the background tmux session."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from meute.claude.context_arg import prepare_context
from meute.claude.launch import claude_argv, find_claude
from meute.claude.mcp_config import write_mcp_config
from meute.claude.settings import MEUTE_TOOLS, write_settings
from meute.cli.context import CliContext
from meute.cli.session_context import session_context
from meute.cli.session_launch import resolve_folder, session_spawn, spawn_and_record
from meute.cli.tmux_env import TmuxEnv, meute_command
from meute.core.config_validate import PERMISSION_MODES
from meute.core.errors import InvalidInput
from meute.core.project import RepoId
from meute.core.session import AgentKind, NewSession, Session, new_session_id
from meute.core.session_state import Unknown
from meute.core.task import TaskId

CLAUDE_MISSING = (
    "claude not found: Claude sessions are disabled;"
    " Bash sessions remain available with --kind bash"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaudeLaunch:
    """What to start: the folder, an optional title, repository, permission mode and task."""

    cwd: Path
    title: str | None = None
    repo_id: RepoId | None = None
    permission_mode: str | None = None
    task_id: TaskId | None = None


def launch_claude(
    ctx: CliContext, env: TmuxEnv, request: ClaudeLaunch, environ: Mapping[str, str]
) -> Session:
    """Start Claude in `meute-bg` with an explicit permission mode and record the session.

    Raises:
        InvalidInput: the folder does not exist, `claude` is missing or the mode is unknown;
            nothing was started and no session was recorded.
        TmuxError: tmux failed.
    """
    cwd = resolve_folder(request.cwd)
    claude = find_claude(environ)
    if claude is None:
        raise InvalidInput(CLAUDE_MISSING)
    session_id = new_session_id()
    title = request.title or cwd.name
    mode = request.permission_mode or ctx.config.claude.permission_mode
    if mode not in PERMISSION_MODES:
        message = f"unknown permission mode: {mode}"
        raise InvalidInput(message)
    command = meute_command()
    settings = write_settings(ctx.paths.state_dir, session_id, command, MEUTE_TOOLS)
    mcp_config = write_mcp_config(ctx.paths.state_dir, session_id, command)
    text = session_context(ctx, project_id=None, repo_id=request.repo_id, task_id=request.task_id)
    context = prepare_context(ctx.paths.state_dir, session_id, text)
    argv = claude_argv(
        claude=claude,
        settings=settings,
        session_id=session_id,
        permission_mode=mode,
        title=title,
        mcp_config=mcp_config,
        context=context,
    )
    return spawn_and_record(
        ctx,
        env,
        session_spawn(session_id, cwd, argv),
        NewSession(
            id=session_id,
            agent=AgentKind.CLAUDE,
            title=title,
            cwd=cwd,
            state=Unknown(),
            repo_id=request.repo_id,
            permission_mode=mode,
            task_id=request.task_id,
        ),
    )
