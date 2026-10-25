"""The project of a new session: an existing one, else the one made for its repository."""

from meute.cli.context import CliContext
from meute.core.db.projects import list_projects
from meute.core.db.repos import create_repo_project, get_repo, repo_project_links
from meute.core.db.tasks import get_task
from meute.core.project import ProjectId, RepoId, name_key
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
    if task_id is not None:
        task_project = get_task(ctx.db, task_id).project
        if task_project is not None:  # read through a join: it exists
            return task_project.id
    repo = None if repo_id is None else get_repo(ctx.db, repo_id)
    if repo is None:
        return None
    found = launch_project_id(
        None, repo, links=repo_project_links(ctx.db), projects=list_projects(ctx.db)
    )
    if found is not None or not name_key(repo.name):
        return found
    return create_repo_project(ctx.db, repo.name).id
