"""`RemoveWorktree` on the board's backend, and resuming a session whose worktree is gone."""

from pathlib import Path

import pytest

from conftest import Sandbox
from git_support import GitRepo, git_env, make_repo, real_git
from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_resume import resume_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import RemoveWorktree
from meute.core.errors import InvalidInput, MeuteError
from meute.git.worktree import remove_worktree
from test_board_backend import _Clock, ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixtures reused
from test_session_resume import _ctx, _ended_claude  # pyright: ignore[reportPrivateUsage] — shared helpers
from test_worktree_removal import linked, recording, removals


@pytest.fixture
def repo(tmp_path: Path) -> GitRepo:
    return make_repo(tmp_path / "repo", git_env(tmp_path))


def _backend(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    environ: dict[str, str],
    cwd: Path,
) -> CliBoardBackend:
    """A backend that loaded once, with a live Bash session in `cwd`."""
    _ = launch_bash(ctx, env, BashLaunch(cwd=cwd), environ)
    backend = CliBoardBackend(ctx, env, environ, monotonic=_Clock())
    _ = backend.load()
    return backend


def test_the_board_never_removes_where_a_live_session_works(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    repo: GitRepo,
    tmp_path: Path,
) -> None:
    path = linked(repo)
    (path / "sub").mkdir()
    environ, log = recording(tmp_path / "bin", repo)
    environ["SHELL"] = "/bin/sh"
    backend = _backend(ctx, env, environ, path / "sub")
    try:
        assert (path / "sub").resolve() in backend.live_folders()
        with pytest.raises(MeuteError, match=r"^a live session works in this worktree$"):
            backend.perform(RemoveWorktree(repo=repo.path, path=path, force=True))
    finally:
        backend.close()
    assert path.is_dir()
    assert removals(log) == []


def test_the_board_removes_a_worktree_and_keeps_its_branch(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    repo: GitRepo,
    tmp_path: Path,
) -> None:
    path = linked(repo)
    other = linked(repo, "other")
    (other / "new.txt").write_text("new\n")
    environ, log = recording(tmp_path / "bin", repo)
    environ["SHELL"] = "/bin/sh"
    backend = _backend(ctx, env, environ, repo.path)
    try:
        assert backend.live_folders() == (repo.path.resolve(), repo.path.resolve())
        with pytest.raises(InvalidInput, match=r"has uncommitted changes or unpushed commits$"):
            backend.perform(RemoveWorktree(repo=repo.path, path=other, force=False))
        with pytest.raises(InvalidInput, match=r"^not a linked worktree: "):
            backend.perform(RemoveWorktree(repo=tmp_path, path=path, force=False))
        assert removals(log) == []
        backend.perform(RemoveWorktree(repo=repo.path, path=path, force=False))
    finally:
        backend.close()
    assert not path.exists()
    assert other.is_dir()
    assert repo.git("branch", "--list", "feat") == "  feat\n"
    assert [line.split("worktree ")[1] for line in removals(log)] == [f"remove {path.resolve()}"]


def test_resuming_a_session_whose_worktree_was_removed_says_folder_not_found(
    sandbox: Sandbox,
) -> None:
    repo = make_repo(sandbox.root / "repo", git_env(sandbox.root))
    repo.git("worktree", "add", "--quiet", "-b", "feat", str(sandbox.root / "w"))
    ended = _ended_claude(sandbox)  # its folder is `w`, the worktree
    remove_worktree(real_git(repo), repo.path, sandbox.root / "w", force=False, environ=repo.env)
    context, tmux_env, environ = _ctx(sandbox)
    try:
        with pytest.raises(InvalidInput, match=r"^folder not found: .*/w$"):
            _ = resume_session(context, tmux_env, ended.id, environ)
    finally:
        context.db.close()
    assert repo.git("branch", "--list", "feat") == "  feat\n"
