"""Board launches with `new_branch`: the worktree is created, then the session runs in it."""

from pathlib import Path

import pytest

from git_support import GitRepo, git_env, make_repo, real_git
from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import BoardAction, LaunchBash, LaunchClaude
from meute.core.db.repos import sync_repos
from meute.core.db.sessions import list_sessions
from meute.core.errors import InvalidInput, MeuteError
from meute.core.project import RepoId
from meute.core.repo import NewRepo
from meute.tmux.layout import ensure_layout
from test_board_backend import _SPEC, _Clock, ctx, env  # noqa: F401 — fixtures  # pyright: ignore[reportUnusedImport, reportPrivateUsage] — fixtures and shared helpers
from test_worktree_launch import REFUSED, files_below, witness


@pytest.fixture
def known(ctx: CliContext, tmp_path: Path) -> tuple[GitRepo, RepoId]:  # noqa: F811 — fixture
    repo = make_repo(tmp_path / "main", git_env(tmp_path))
    (row,) = sync_repos(ctx.db, [NewRepo(path=repo.path.resolve(), name="main", kind=None)])
    return repo, row.id


def _perform(ctx: CliContext, env: TmuxEnv, environ: dict[str, str], action: BoardAction) -> None:  # noqa: F811 — fixtures
    _ = ensure_layout(env.tmux, _SPEC)
    backend = CliBoardBackend(ctx, env, {**environ, "SHELL": "/bin/sh"}, monotonic=_Clock())
    try:
        backend.perform(action)
    finally:
        backend.close()


def test_a_bash_session_runs_in_the_new_worktree(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    known: tuple[GitRepo, RepoId],
) -> None:
    repo, repo_id = known
    action = LaunchBash(cwd=repo.path, repo_id=repo_id, new_branch="feat/x")
    _perform(ctx, env, dict(repo.env), action)
    (session,) = list_sessions(ctx.db)
    path = (repo.path.parent / "main.worktrees" / "feat" / "x").resolve()
    assert (session.cwd, session.repo_id) == (path, repo_id)
    assert repo.git("rev-parse", "feat/x") == repo.git("rev-parse", "HEAD")


def test_an_existing_branch_launches_nothing(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    known: tuple[GitRepo, RepoId],
) -> None:
    repo, repo_id = known
    repo.git("branch", "x")
    action = LaunchBash(cwd=repo.path, repo_id=repo_id, new_branch="x")
    with pytest.raises(MeuteError, match=r"^git: fatal: a branch named 'x' already exists$"):
        _perform(ctx, env, dict(repo.env), action)
    assert list_sessions(ctx.db, include_ended=True) == []


def test_a_new_worktree_needs_a_repository(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    folder, log = witness(tmp_path / "bin")
    action = LaunchBash(cwd=tmp_path, repo_id=None, new_branch="x")
    with pytest.raises(InvalidInput, match=r"^a new worktree needs a repository$"):
        _perform(ctx, env, {"PATH": str(folder)}, action)
    assert not log.exists()


@pytest.mark.parametrize("branch", REFUSED)
def test_a_refused_name_creates_nothing_and_never_adds(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    known: tuple[GitRepo, RepoId],
    branch: str,
) -> None:
    repo, repo_id = known
    folder, log = witness(repo.path.parent / "bin")
    before = files_below(repo.path.parent)
    action = LaunchClaude(cwd=repo.path, repo_id=repo_id, new_branch=branch)
    with pytest.raises(InvalidInput):
        _perform(ctx, env, {"PATH": str(folder)}, action)
    assert not log.exists()
    assert files_below(repo.path.parent) == before
    assert list_sessions(ctx.db, include_ended=True) == []


def test_a_failed_launch_tells_where_the_worktree_is(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    known: tuple[GitRepo, RepoId],
) -> None:
    repo, repo_id = known
    only_git = repo.path.parent / "only-git"
    only_git.mkdir()
    (only_git / "git").symlink_to(real_git(repo))
    action = LaunchClaude(cwd=repo.path, repo_id=repo_id, new_branch="x")
    path = repo.path.parent / "main.worktrees" / "x"
    with pytest.raises(MeuteError) as raised:
        _perform(ctx, env, {**repo.env, "PATH": str(only_git)}, action)
    assert str(raised.value).startswith(
        f"worktree created at {path} but the launch failed: claude not found: "
    )
    assert path.is_dir()
    assert list_sessions(ctx.db, include_ended=True) == []
