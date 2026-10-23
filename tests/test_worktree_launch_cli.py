"""`meute session new --worktree`: the session runs in a new worktree of the folder's repository."""

import os
import shutil
from pathlib import Path

import pytest

from conftest import FAKE_CLAUDE_DIR, Sandbox
from git_support import GitRepo, git_env, make_repo
from meute.core.db.repos import sync_repos
from meute.core.db.sessions import list_sessions
from meute.core.repo import NewRepo
from test_worktree_launch import REFUSED, files_below, witness

_PINNED = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME")


def _repo(sandbox: Sandbox) -> GitRepo:
    return make_repo((sandbox.root / "repo").resolve(), git_env(sandbox.root))


def _git_only(repo: GitRepo) -> dict[str, str]:
    """The pinned git configuration, without the sandbox's own HOME and PATH."""
    return {key: repo.env[key] for key in _PINNED}


def test_the_session_runs_in_the_new_worktree(sandbox: Sandbox) -> None:
    repo = _repo(sandbox)
    with sandbox.db() as db:
        (known,) = sync_repos(db, [NewRepo(path=repo.path, name="repo", kind=None)])
    nested = repo.path / "src"
    nested.mkdir()
    result = sandbox.run(
        "session", "new", "--kind", "bash", "--cwd", str(nested), "--worktree", "feat/x",
        env=_git_only(repo),
    )  # fmt: skip
    path = repo.path.parent / "repo.worktrees" / "feat" / "x"
    assert result.returncode == 0, result.stderr
    assert result.stdout.endswith(f" x ({path})\n")
    with sandbox.db() as db:
        (session,) = list_sessions(db)
    assert (session.cwd, session.repo_id) == (path, known.id)
    assert repo.git("status", "--porcelain") == ""


def test_outside_git_is_refused(sandbox: Sandbox) -> None:
    folder = (sandbox.root / "plain").resolve()
    folder.mkdir()
    result = sandbox.run("session", "new", "--kind", "bash", "--cwd", str(folder), "--worktree=x")
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == f"meute: not in a git repository: {folder}\n"
    assert not sandbox.tmux().is_running()


def test_an_existing_branch_launches_nothing(sandbox: Sandbox) -> None:
    repo = _repo(sandbox)
    repo.git("branch", "x")
    result = sandbox.run(
        "session", "new", "--kind", "bash", "--cwd", str(repo.path), "--worktree=x",
        env=_git_only(repo),
    )  # fmt: skip
    assert result.returncode == 1
    assert result.stderr == "meute: git: fatal: a branch named 'x' already exists\n"
    assert not sandbox.tmux().is_running()


@pytest.mark.parametrize("branch", REFUSED)
def test_a_refused_name_creates_nothing_and_never_adds(sandbox: Sandbox, branch: str) -> None:
    repo = _repo(sandbox)
    folder, log = witness(sandbox.root / "bin")
    before = files_below(repo.path.parent)
    result = sandbox.run(
        "session", "new", "--kind", "bash", "--cwd", str(repo.path), f"--worktree={branch}",
        env={"PATH": f"{folder}:{FAKE_CLAUDE_DIR}:{os.environ.get('PATH', '')}"},
    )  # fmt: skip
    assert result.returncode == 1, result.stderr
    assert not log.exists()
    assert {p for p in files_below(repo.path.parent) if "repo.worktrees" in p.parts} == set()
    assert not before - files_below(repo.path.parent)
    assert not sandbox.tmux().is_running()


def test_a_failed_launch_keeps_the_worktree(sandbox: Sandbox, tmp_path: Path) -> None:
    repo = _repo(sandbox)
    no_claude = tmp_path / "no-claude"  # git and tmux, but no claude
    no_claude.mkdir()
    for tool in ("git", "tmux"):
        found = shutil.which(tool)
        assert found is not None
        (no_claude / tool).symlink_to(found)
    result = sandbox.run(
        "session", "new", "--cwd", str(repo.path), "--worktree=x",
        env={**_git_only(repo), "PATH": str(no_claude)},
    )  # fmt: skip
    path = repo.path.parent / "repo.worktrees" / "x"
    assert result.returncode == 1
    assert result.stderr.startswith(
        f"meute: worktree created at {path} but the launch failed: claude not found: "
    )
    assert path.is_dir()
