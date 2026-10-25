"""The project of a new session: an existing one, else the one made for its repository."""

from meute.cli.context import CliContext
from meute.core.db.projects import list_projects
from meute.core.db.repos import create_repo_project, list_repos, repo_project_links
from meute.core.db.tasks import get_task
from meute.core.project import ProjectId, RepoId
from meute.core.session_project import launch_project_id
from meute.core.task import TaskId


def launch_project(
    ctx: CliContext, *, repo_id: RepoId | None, task_id: TaskId | None
) -> ProjectId | None:
    """Return the project a new session belongs to, creating the repository's if it has none.

    The task's project comes first, then the repository's linked project, then the project
    named like the repository; failing all three, a project is created for a known
    repository whose name is not blank. `None` when there is none of these.

    Raises:
        NotFound: no such task.
        sqlite3.Error: the database failed.
    """
    task_project = None if task_id is None else get_task(ctx.db, task_id).project
    repo = (
        None if repo_id is None else next((r for r in list_repos(ctx.db) if r.id == repo_id), None)
    )
    found = launch_project_id(
        None if task_project is None else task_project.id,
        repo,
        links=repo_project_links(ctx.db),
        projects=list_projects(ctx.db),
    )
    if found is not None or repo is None or not repo.name.strip():
        return found
    return create_repo_project(ctx.db, repo.name.strip()).id
