"""Launches and adoption find the repository of a folder, linked worktrees included."""

from pathlib import Path

from git_support import GitRepo, git_env, make_repo
from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.orphan_actions import adopt_orphan
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import LaunchBash
from meute.core.db.repos import sync_repos
from meute.core.db.sessions import list_sessions
from meute.core.project import RepoId
from meute.core.repo import NewRepo
from meute.core.session import new_session_id
from meute.tmux.layout import ensure_layout
from test_board_backend import _ENVIRON, _SPEC, _Clock, ctx, env  # noqa: F401 — fixtures  # pyright: ignore[reportUnusedImport, reportPrivateUsage] — fixtures and shared helpers
from test_orphan_actions import _orphan_pane  # pyright: ignore[reportPrivateUsage] — shared helper


def _known_repo(ctx: CliContext, tmp_path: Path) -> tuple[GitRepo, Path, RepoId]:  # noqa: F811 — fixture name
    repo = make_repo(tmp_path / "main", git_env(tmp_path))
    worktree = tmp_path / "feature"
    repo.git("worktree", "add", "--quiet", "-b", "feature", str(worktree))
    repos = sync_repos(ctx.db, [NewRepo(path=repo.path.resolve(), name="main", kind=None)])
    (known,) = repos
    return repo, worktree.resolve(), known.id


def _launch(ctx: CliContext, env: TmuxEnv, cwd: Path, repo_id: RepoId | None) -> RepoId | None:  # noqa: F811 — fixtures
    _ = ensure_layout(env.tmux, _SPEC)
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    backend.perform(LaunchBash(cwd=cwd, repo_id=repo_id))
    return list_sessions(ctx.db)[-1].repo_id


def test_a_launch_in_a_linked_worktree_records_the_main_repository(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    _, worktree, known = _known_repo(ctx, tmp_path)
    assert _launch(ctx, env, worktree, None) == known


def test_a_launch_in_a_nested_folder_records_the_repository(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    repo, _, known = _known_repo(ctx, tmp_path)
    nested = repo.path / "src"
    nested.mkdir()
    assert _launch(ctx, env, nested, None) == known


def test_an_explicit_repository_wins(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    _, worktree, known = _known_repo(ctx, tmp_path)
    (other,) = (
        r.id
        for r in sync_repos(ctx.db, [NewRepo(path=tmp_path / "other", name="other", kind=None)])
        if r.id != known
    )
    assert _launch(ctx, env, worktree, other) == other


def test_adopting_an_orphan_in_a_linked_worktree_records_the_main_repository(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    _, worktree, known = _known_repo(ctx, tmp_path)
    session = adopt_orphan(ctx, _orphan_pane(env, worktree, str(new_session_id())))
    assert session is not None
    assert session.repo_id == known
