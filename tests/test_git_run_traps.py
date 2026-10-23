"""Hostile repository configuration never runs code through a guarded read."""

import os
import subprocess
from pathlib import Path

import pytest

from git_support import GitRepo, fake_git, make_repo, real_git
from meute.git.run import GitError, read_args, read_git, start_read, write_git


def test_trapped_config_runs_nothing(git_repo: GitRepo, tmp_path: Path) -> None:
    witness = tmp_path / "witness"
    trap = fake_git(tmp_path / "trap", f'touch "{witness}"\ncat "$2" 2>/dev/null\nexit 0')
    git_repo.git("config", "core.fsmonitor", str(trap))
    git_repo.git("config", "diff.x.command", str(trap))
    git_repo.git("config", "diff.x.textconv", str(trap))
    (git_repo.path / ".gitattributes").write_text("* diff=x\n")
    (git_repo.path / "README.md").write_text("hello\nchanged\n")
    for unguarded in (["status"], ["diff", "HEAD"]):
        git_repo.git(*unguarded)
        assert witness.exists(), f"git {unguarded[0]} must fire the trap without the guard"
        witness.unlink()
    git = real_git(git_repo)
    for args in (["status", "--porcelain=v2", "--branch"], ["diff", "HEAD"]):
        read_git(git, git_repo.path, args, timeout=5, environ=git_repo.env)
    numstat = read_git(
        git, git_repo.path, ["diff", "--numstat", "HEAD"], timeout=5, environ=git_repo.env
    )
    assert numstat == "1\t0\tREADME.md\n"
    assert not witness.exists()


def unguarded_read(repo: GitRepo, args: list[str]) -> None:
    """The read without the filter neutralisation, as before the fix: it may fail."""
    subprocess.run(
        [real_git(repo), *read_args(repo.path, args)],
        capture_output=True,
        env=dict(repo.env),
        check=False,
    )


@pytest.mark.parametrize(
    ("driver", "key"), [("x", "clean"), ("x", "process"), ("x.y", "clean"), ("x.y", "process")]
)
def test_filter_drivers_never_run(git_repo: GitRepo, tmp_path: Path, driver: str, key: str) -> None:
    witness = tmp_path / "witness"
    trap = fake_git(tmp_path / "trap", f'touch "{witness}"\ncat')
    (git_repo.path / ".gitattributes").write_text(f"* filter={driver}\n")
    git_repo.git("add", ".gitattributes")
    git_repo.git("commit", "--quiet", "--message=attributes")
    git_repo.git("config", "filter.other.smudge", "unused")
    git_repo.git("config", f"filter.{driver}.{key}", str(trap))
    git_repo.git("config", f"filter.{driver}.required", "true")
    readme = git_repo.path / "README.md"
    stale = readme.stat().st_mtime + 10
    os.utime(readme, (stale, stale))  # same content, stat data out of date in the index
    git = real_git(git_repo)
    status = ["status", "--porcelain=v2"]
    numstat = ["diff", "--numstat", "HEAD"]
    unguarded_read(git_repo, status)
    assert witness.exists(), "the trap must fire on status without the neutralisation"
    witness.unlink()
    assert read_git(git, git_repo.path, status, timeout=5, environ=git_repo.env) == ""
    assert not witness.exists()
    readme.write_text("hello\nchanged\n")
    unguarded_read(git_repo, numstat)
    assert witness.exists(), "the trap must fire on diff without the neutralisation"
    witness.unlink()
    out = read_git(git, git_repo.path, numstat, timeout=5, environ=git_repo.env)
    assert out == "1\t0\tREADME.md\n"
    process = start_read(git, git_repo.path, numstat, environ=git_repo.env)
    assert process.communicate(timeout=5)[0] == b"1\t0\tREADME.md\n"
    assert not witness.exists()


def test_a_driver_name_git_c_cannot_express_is_refused(git_repo: GitRepo, tmp_path: Path) -> None:
    witness = tmp_path / "witness"
    trap = fake_git(tmp_path / "trap", f'touch "{witness}"\ncat')
    (git_repo.path / ".gitattributes").write_text("* filter=a=b\n")
    git_repo.git("config", "filter.a=b.clean", str(trap))
    (git_repo.path / "README.md").write_text("hello\nchanged\n")
    git = real_git(git_repo)
    with pytest.raises(GitError) as caught:
        read_git(git, git_repo.path, ["diff", "--numstat", "HEAD"], timeout=5, environ=git_repo.env)
    assert str(caught.value) == "git: unsupported filter driver name"
    with pytest.raises(GitError):
        start_read(git, git_repo.path, ["status"], environ=git_repo.env)
    assert not witness.exists()


def test_submodules_are_ignored(git_repo: GitRepo, tmp_path: Path) -> None:
    witness = tmp_path / "witness"
    trap = fake_git(tmp_path / "trap", f'touch "{witness}"\ncat')
    sub = make_repo(tmp_path / "sub", git_repo.env)
    (sub.path / ".gitattributes").write_text("* filter=x\n")
    sub.git("add", ".gitattributes")
    sub.git("commit", "--quiet", "--message=attributes")
    git_repo.git(
        "-c", "protocol.file.allow=always", "submodule", "--quiet", "add", str(sub.path), "sub"
    )
    git_repo.git("commit", "--quiet", "--message=submodule")
    inner = git_repo.path / "sub"
    GitRepo(path=inner, env=git_repo.env).git("config", "filter.x.clean", str(trap))
    stale = (inner / "README.md").stat().st_mtime + 10
    os.utime(inner / "README.md", (stale, stale))  # the submodule's own filter would run
    git = real_git(git_repo)
    status = ["status", "--porcelain=v2"]
    subprocess.run(
        [git, "--no-optional-locks", "-C", git_repo.path, *status],
        capture_output=True,
        env=dict(git_repo.env),
        check=True,
    )
    assert witness.exists(), "the submodule's trap must fire without the guard"
    witness.unlink()
    for args in (status, ["diff", "--numstat", "HEAD"]):
        assert read_git(git, git_repo.path, args, timeout=5, environ=git_repo.env) == ""
    assert not witness.exists()


def test_write_git_keeps_hooks_but_not_fsmonitor(git_repo: GitRepo, tmp_path: Path) -> None:
    hooked = tmp_path / "hooked"
    trapped = tmp_path / "trapped"
    hook = git_repo.path / ".git/hooks/post-checkout"
    hook.write_text(f'#!/bin/sh\ntouch "{hooked}"\n')
    hook.chmod(0o755)
    trap = fake_git(tmp_path / "trap", f'touch "{trapped}"\nexit 1')
    git_repo.git("config", "core.fsmonitor", str(trap))
    worktree = tmp_path / "feat"
    write_git(
        real_git(git_repo),
        git_repo.path,
        ["worktree", "add", "-b", "feat", str(worktree)],
        timeout=30,
        environ=git_repo.env,
    )
    assert (worktree / "README.md").exists()
    assert hooked.exists()
    assert not trapped.exists()
