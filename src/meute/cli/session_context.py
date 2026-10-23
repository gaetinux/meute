"""What a Claude session starts with: its files, its permission mode and its context."""

from dataclasses import dataclass
from pathlib import Path

from meute.claude.context_arg import ContextArg, prepare_context
from meute.claude.mcp_config import write_mcp_config
from meute.claude.settings import MEUTE_TOOLS, write_settings
from meute.cli.context import CliContext
from meute.cli.tmux_env import meute_command
from meute.core.config import load_config
from meute.core.config_validate import PERMISSION_MODES
from meute.core.context import compose_context
from meute.core.db.projects import list_projects
from meute.core.db.repos import list_repos
from meute.core.errors import InvalidInput
from meute.core.project import Project, ProjectId, RepoId
from meute.core.session import SessionId
from meute.core.session_project import project_of
from meute.core.task import TaskId


def _project(
    ctx: CliContext, project_id: ProjectId | None, repo_id: RepoId | None
) -> Project | None:
    projects = list_projects(ctx.db)
    own = project_id is not None and any(p.id == project_id for p in projects)
    repos = {} if own or repo_id is None else {r.id: r for r in list_repos(ctx.db)}
    return project_of(project_id, repo_id, projects=projects, repos=repos)


def session_context(
    ctx: CliContext,
    *,
    instructions: str,
    project_id: ProjectId | None,
    repo_id: RepoId | None,
    task_id: TaskId | None,
) -> str | None:
    """Compose the context of a session that may not be recorded yet; None when empty.

    `instructions` are the global ones. The project and its instructions are read from the
    database at each call.
    """
    return compose_context(
        global_instructions=instructions,
        project=_project(ctx, project_id, repo_id),
        task_id=task_id,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaudeStart:
    """The permission mode, the files and the context a Claude session starts with."""

    permission_mode: str
    settings: Path
    mcp_config: Path
    context: ContextArg | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaudeOrigin:
    """What the session belongs to and the mode asked for (None: the configured one)."""

    project_id: ProjectId | None = None
    repo_id: RepoId | None = None
    task_id: TaskId | None = None
    permission_mode: str | None = None


def prepare_claude(ctx: CliContext, session_id: SessionId, origin: ClaudeOrigin) -> ClaudeStart:
    """Write the settings, the MCP configuration and the context of a session.

    The configuration is read again first, before any file is written: the board keeps one
    context for its whole life, and its default permission mode and global instructions may
    have changed since.

    Raises:
        ConfigError: the configuration file has become invalid; nothing was written.
        InvalidInput: the permission mode is unknown; nothing was written.
    """
    config = load_config(ctx.paths.config_file)
    mode = origin.permission_mode or config.claude.permission_mode
    if mode not in PERMISSION_MODES:
        message = f"unknown permission mode: {mode}"
        raise InvalidInput(message)
    command = meute_command()
    settings = write_settings(ctx.paths.state_dir, session_id, command, MEUTE_TOOLS)
    mcp_config = write_mcp_config(ctx.paths.state_dir, session_id, command)
    text = session_context(
        ctx,
        instructions=config.claude.instructions,
        project_id=origin.project_id,
        repo_id=origin.repo_id,
        task_id=origin.task_id,
    )
    return ClaudeStart(
        permission_mode=mode,
        settings=settings,
        mcp_config=mcp_config,
        context=prepare_context(ctx.paths.state_dir, session_id, text),
    )
