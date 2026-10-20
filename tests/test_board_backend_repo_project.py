"""`@name` naming a known repository: the task's project is created from that repository."""

from pathlib import Path

import pytest

from meute.cli.context import CliContext
from meute.cli.task_quick import CliQuickBackend
from meute.cli.task_quick_create import create_quick_task
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import CreateTask, MoveToRepoProject
from meute.core.db.projects import list_projects
from meute.core.db.repos import list_repos, sync_repos
from meute.core.db.task_reads import project_repo_ids
from meute.core.db.tasks import TaskFilter, create_task, get_task, list_tasks
from meute.core.errors import InvalidInput, VersionConflict
from meute.core.project import ProjectRef
from meute.core.repo import NewRepo
from support import USER, new_task
from test_board_backend import env  # noqa: F401 — fixture reused  # pyright: ignore[reportUnusedImport] — fixture reused
from test_board_backend_tasks import _backend, ctx  # noqa: F401 — fixture reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixture reused

REPO = Path("/g/poc-app-rust")


@pytest.fixture
def repo_ctx(ctx: CliContext) -> CliContext:  # noqa: F811 — fixture
    _ = sync_repos(ctx.db, [NewRepo(path=REPO, name="poc-app-rust", kind=None)])
    return ctx


def _project(cli: CliContext) -> ProjectRef:
    """The only project, named after the repository and attached to it."""
    (project,) = list_projects(cli.db)
    assert [
        repo.path for repo in list_repos(cli.db) if repo.id in project_repo_ids(cli.db, project.id)
    ] == [REPO]
    return ProjectRef(id=project.id, name="poc-app-rust")


def test_quick_entry_creates_the_project_of_the_repository(repo_ctx: CliContext) -> None:
    task = create_quick_task(repo_ctx, "Fix CI @POC-app-rust", None)
    assert task.project == _project(repo_ctx)


def test_an_empty_title_writes_no_project(repo_ctx: CliContext) -> None:
    with pytest.raises(InvalidInput):
        create_quick_task(repo_ctx, " @poc-app-rust !", None)
    assert list_projects(repo_ctx.db) == []
    assert list_tasks(repo_ctx.db, TaskFilter()) == []


def test_an_existing_project_is_reused_not_recreated(repo_ctx: CliContext) -> None:
    create_quick_task(repo_ctx, "One @poc-app-rust", None)
    create_quick_task(repo_ctx, "Two @poc-app-rust", None)
    assert len(list_projects(repo_ctx.db)) == 1


def test_the_board_creates_it_too(repo_ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    _backend(repo_ctx, env).perform(CreateTask(text="Board @poc-app-rust", project=None))
    (task,) = list_tasks(repo_ctx.db, TaskFilter())
    assert task.project == _project(repo_ctx)


def test_the_quick_window_previews_and_creates_it(repo_ctx: CliContext) -> None:
    backend = CliQuickBackend(repo_ctx, None, ())  # the projects listed when it opened
    assert backend.context().repo_names == ("poc-app-rust",)
    task = backend.create("Window @poc-app-rust")
    assert task.project == _project(repo_ctx)


def test_moving_a_task_to_a_repository_creates_its_project(
    repo_ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
) -> None:
    task = create_task(repo_ctx.db, new_task("Move me"), USER)
    action = MoveToRepoProject(task_id=task.id, version=1, name="poc-app-rust")
    _backend(repo_ctx, env).perform(action)
    assert get_task(repo_ctx.db, task.id).project == _project(repo_ctx)


def test_a_stale_move_is_a_version_conflict(repo_ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    task = create_task(repo_ctx.db, new_task("Move me"), USER)
    with pytest.raises(VersionConflict):
        _backend(repo_ctx, env).perform(
            MoveToRepoProject(task_id=task.id, version=7, name="poc-app-rust")
        )
    assert get_task(repo_ctx.db, task.id).project is None
    assert list_projects(repo_ctx.db) == []  # the version is checked before the project is made


def test_a_stale_project_list_reuses_the_project_made_meanwhile(repo_ctx: CliContext) -> None:
    first = create_quick_task(repo_ctx, "One @poc-app-rust", None, projects=())
    second = create_quick_task(repo_ctx, "Two @poc-app-rust", None, projects=())
    assert first.project == second.project == _project(repo_ctx)
