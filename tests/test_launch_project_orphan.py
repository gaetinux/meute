"""Adopting an orphan pane in a known repository creates no project."""

from pathlib import Path

from meute.cli.context import CliContext
from meute.cli.orphan_actions import adopt_orphan
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.projects import list_projects
from meute.core.db.repos import sync_repos
from meute.core.repo import NewRepo
from meute.core.session import new_session_id
from test_board_backend import ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportUnusedImport] — fixtures reused
from test_orphan_actions import _orphan_pane  # pyright: ignore[reportPrivateUsage] — shared helper


def test_adopting_an_orphan_in_a_known_repository_creates_no_project(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    folder = tmp_path.resolve()
    _ = sync_repos(ctx.db, [NewRepo(path=folder, name="alpha", kind=None)])
    orphan = _orphan_pane(env, folder, str(new_session_id()))
    assert adopt_orphan(ctx, orphan) is not None
    assert list_projects(ctx.db) == []
