"""The context appended to the system prompt of a Claude session."""

from meute.cli.context import CliContext
from meute.core.context import compose_context
from meute.core.db.projects import list_projects
from meute.core.db.repos import list_repos
from meute.core.project import Project, ProjectId, RepoId
from meute.core.task import TaskId


def _project(
    ctx: CliContext, project_id: ProjectId | None, repo_id: RepoId | None
) -> Project | None:
    """The project itself, else the one named like the repository (ignoring case)."""
    projects = list_projects(ctx.db)
    for project in projects:
        if project.id == project_id:
            return project
    repo = next((r for r in list_repos(ctx.db) if r.id == repo_id), None)
    if repo is None:
        return None
    key = repo.name.casefold()
    return next((p for p in projects if p.name.casefold() == key), None)


def session_context(
    ctx: CliContext, *, project_id: ProjectId | None, repo_id: RepoId | None, task_id: TaskId | None
) -> str | None:
    """Compose the context of a session that may not be recorded yet; None when empty."""
    return compose_context(
        global_instructions=ctx.config.claude.instructions,
        project=_project(ctx, project_id, repo_id),
        task_id=task_id,
    )
