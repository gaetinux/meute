"""Launching a Claude Code session in the background tmux session."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from meute.claude.launch import claude_argv, find_claude
from meute.cli.context import CliContext
from meute.cli.session_context import ClaudeOrigin, prepare_claude
from meute.cli.session_launch import (
    BashLaunch,
    launch_bash,
    resolve_folder,
    session_spawn,
    spawn_and_record,
)
from meute.cli.tmux_env import TmuxEnv
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
        ConfigError: the configuration file has become invalid; nothing was started.
        TmuxError: tmux failed.
    """
    cwd = resolve_folder(request.cwd)
    claude = find_claude(environ)
    if claude is None:
        raise InvalidInput(CLAUDE_MISSING)
    session_id = new_session_id()
    title = request.title or cwd.name
    origin = ClaudeOrigin(
        repo_id=request.repo_id, task_id=request.task_id, permission_mode=request.permission_mode
    )
    start = prepare_claude(ctx, session_id, origin)
    argv = claude_argv(
        claude=claude,
        settings=start.settings,
        session_id=session_id,
        permission_mode=start.permission_mode,
        title=title,
        mcp_config=start.mcp_config,
        context=start.context,
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
            permission_mode=start.permission_mode,
            task_id=request.task_id,
        ),
    )


def start_session(  # noqa: PLR0913 — what a launch of either kind needs
    ctx: CliContext,
    env: TmuxEnv,
    environ: Mapping[str, str],
    *,
    kind: AgentKind,
    cwd: Path,
    repo_id: RepoId | None,
    title: str | None,
    permission_mode: str | None,
) -> Session:
    """Start a `kind` session in `cwd` (see `launch_claude` and `launch_bash`).

    `permission_mode` only applies to Claude.

    Raises:
        InvalidInput: the folder does not exist, `claude` is missing or the mode is unknown.
        ConfigError: the configuration file has become invalid; nothing was started.
        TmuxError: tmux failed.
    """
    match kind:
        case AgentKind.CLAUDE:
            claude = ClaudeLaunch(
                cwd=cwd, repo_id=repo_id, title=title, permission_mode=permission_mode
            )
            return launch_claude(ctx, env, claude, environ)
        case AgentKind.BASH:
            bash = BashLaunch(cwd=cwd, repo_id=repo_id, title=title)
            return launch_bash(ctx, env, bash, environ)
        case _:
            assert_never(kind)
