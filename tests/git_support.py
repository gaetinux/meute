"""Throw-away git repositories with a pinned git environment (never the author's repos)."""

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

from meute.git.run import find_git


def git_env(root: Path) -> dict[str, str]:
    """A git environment confined to `root`: no user or system configuration, fixed identity."""
    home = root / "git-home"
    home.mkdir(exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Test Author",
        "GIT_AUTHOR_EMAIL": "author@example.invalid",
        "GIT_AUTHOR_DATE": "2026-10-14T10:30:00+02:00",
        "GIT_COMMITTER_NAME": "Test Committer",
        "GIT_COMMITTER_EMAIL": "committer@example.invalid",
        "GIT_COMMITTER_DATE": "2026-10-14T10:30:00+02:00",
        "LC_ALL": "C",
    }


@dataclass(frozen=True, slots=True, kw_only=True)
class GitRepo:
    """A repository below `tmp_path` and the environment its git commands run with."""

    path: Path
    env: Mapping[str, str]

    def git(self, *args: str) -> str:
        """Run `git -C <path> <args>` with the pinned environment; fail the test on error."""
        done = subprocess.run(
            ["git", "-C", str(self.path), *args],  # noqa: S607 — the test git, from the PATH
            capture_output=True,
            text=True,
            env=dict(self.env),
            check=False,
        )
        if done.returncode != 0:
            pytest.fail(f"git {' '.join(args)} failed: {done.stderr}", pytrace=False)
        return done.stdout


def make_repo(path: Path, env: Mapping[str, str]) -> GitRepo:
    """Create a repository at `path` on branch `main` with one commit of `README.md`."""
    path.mkdir(parents=True, exist_ok=True)
    repo = GitRepo(path=path, env=env)
    repo.git("init", "--quiet", "--initial-branch=main")
    (path / "README.md").write_text("hello\n")
    repo.git("add", "README.md")
    repo.git("commit", "--quiet", "--message=init")
    return repo


@pytest.fixture
def git_repo(tmp_path: Path) -> GitRepo:
    """A fresh repository at `tmp_path / "repo"` with one commit."""
    return make_repo(tmp_path / "repo", git_env(tmp_path))


def fake_git(folder: Path, body: str) -> Path:
    """Write an executable `folder/git` shell script running `body`."""
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "git"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)
    return script


def real_git(repo: GitRepo) -> Path:
    """The real git found on the PATH of `repo`'s environment."""
    git = find_git(repo.env)
    assert git is not None
    return git
