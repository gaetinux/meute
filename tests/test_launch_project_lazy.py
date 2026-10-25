"""`launch_project` reads only what its rules need, in their order."""

from pathlib import Path

import pytest

from conftest import Sandbox
from meute.cli import launch_project as module
from meute.cli.launch_project import launch_project
from meute.core.db.projects import create_project
from meute.core.db.repos import sync_repos
from meute.core.db.tasks import create_task
from meute.core.repo import NewRepo
from support import USER, new_task
from test_launch_context import _ctx  # pyright: ignore[reportPrivateUsage] — shared helper


def _unread(*_args: object) -> object:
    raise AssertionError


def test_a_task_project_stops_before_the_repository_tables(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, _ = _ctx(sandbox)
    try:
        (repo,) = sync_repos(ctx.db, [NewRepo(path=Path("/g/web"), name="web", kind=None)])
        api = create_project(ctx.db, "api")
        task = create_task(ctx.db, new_task("Do it", api.id), USER)
        for name in ("get_repo", "repo_project_links", "list_projects"):
            monkeypatch.setattr(module, name, _unread)
        assert launch_project(ctx, repo_id=repo.id, task_id=task.id) == api.id
    finally:
        ctx.db.close()
