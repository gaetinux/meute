import os
import subprocess
import time
from pathlib import Path

import pytest

from git_support import GitRepo, fake_git, git_env, real_git
from meute.git.discover import main_repo_of
from meute.git.run import GitError, find_git, read_args, read_git, start_read_with, write_git

GUARD = ("-c", "core.fsmonitor=false", "--no-optional-locks")


ECHO = 'printf "%s\\n" "$@"'


def test_read_args_guard_status() -> None:
    assert read_args(Path("/r"), ["status", "--porcelain=v2", "--branch"]) == (
        *GUARD,
        "-C",
        "/r",
        "status",
        "--ignore-submodules=all",
        "--porcelain=v2",
        "--branch",
    )


def test_read_args_disable_external_diff_and_textconv() -> None:
    assert read_args(Path("/r"), ["diff", "--numstat", "HEAD"]) == (
        *GUARD,
        "-C",
        "/r",
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=all",
        "--numstat",
        "HEAD",
    )


def test_read_args_neutralise_the_given_filter_drivers() -> None:
    assert read_args(Path("/r"), ["status"], filters=["x", "a.b"]) == (
        "-c",
        "core.fsmonitor=false",
        "-c",
        "filter.x.clean=",
        "-c",
        "filter.x.process=",
        "-c",
        "filter.x.required=false",
        "-c",
        "filter.a.b.clean=",
        "-c",
        "filter.a.b.process=",
        "-c",
        "filter.a.b.required=false",
        "--no-optional-locks",
        "-C",
        "/r",
        "status",
        "--ignore-submodules=all",
    )


def test_relative_folder_is_a_programming_error(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", "exit 0")
    with pytest.raises(ValueError, match="absolute"):
        read_args(Path("r"), ["status"])
    with pytest.raises(ValueError, match="absolute"):
        write_git(git, Path("r"), ["worktree", "list"], timeout=5, environ={})


def test_read_git_passes_the_guarded_args_and_environment(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", f"{ECHO}\necho --\n/usr/bin/env")
    environ = {"PATH": "/some/bin", "HOME": "/some/home", "GIT_OPTIONAL_LOCKS": "1"}
    out = read_git(git, tmp_path, ["status"], timeout=5, environ=environ)
    args, _, env = out.partition("--\n")
    assert tuple(args.splitlines()) == read_args(tmp_path, ["status"])
    variables = set(env.splitlines())
    assert {
        "GIT_TERMINAL_PROMPT=0",
        "GIT_OPTIONAL_LOCKS=0",
        "PATH=/some/bin",
        "HOME=/some/home",
    } <= variables


def test_read_git_decodes_with_replacement(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", "printf 'a\\377b'")
    assert read_git(git, tmp_path, ["status"], timeout=5, environ={}) == "a�b"


def test_failure_reports_the_first_line_of_git(git_repo: GitRepo, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(GitError) as caught:
        read_git(real_git(git_repo), plain, ["status"], timeout=5, environ=git_repo.env)
    assert str(caught.value).startswith("git: fatal: not a git repository")
    assert "\n" not in str(caught.value)


def test_failure_message_is_bounded(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", "printf '%0500d\\nsecond\\n' 0 >&2\nexit 3")
    with pytest.raises(GitError) as caught:
        read_git(git, tmp_path, ["status"], timeout=5, environ={})
    assert str(caught.value) == "git: " + "0" * 200


def test_failure_without_message_gives_the_status(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", "exit 3")
    with pytest.raises(GitError) as caught:
        read_git(git, tmp_path, ["status"], timeout=5, environ={})
    assert str(caught.value) == "git: exit status 3"


def test_timeout_kills_git_and_its_children(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    git = fake_git(tmp_path / "bin", f'echo $$ > "{pids}"\nsleep 30 &\necho $! >> "{pids}"\nwait')
    started = time.monotonic()
    with pytest.raises(GitError) as caught:
        read_git(git, tmp_path, ["status"], timeout=1, environ=dict(os.environ))
    assert time.monotonic() - started < 5  # the child holding the pipes was killed too
    assert str(caught.value) == "git timed out after 1 s"
    shell, child = (int(pid) for pid in pids.read_text().split())
    assert not Path(f"/proc/{shell}").exists()  # killed and reaped
    deadline = time.monotonic() + 3
    while is_alive(child) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not is_alive(child)


def is_alive(pid: int) -> bool:
    """Whether `pid` runs: neither gone nor a zombie waiting for its parent."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[0]
    except OSError:
        return False
    return state != "Z"


def test_missing_git(tmp_path: Path) -> None:
    with pytest.raises(GitError) as caught:
        read_git(tmp_path / "nowhere/git", tmp_path, ["status"], timeout=5, environ={})
    assert str(caught.value) == "git not found"


def test_find_git(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", "exit 0")
    assert find_git({"PATH": f"{tmp_path / 'empty'}:{git.parent}"}) == git
    assert find_git({"PATH": str(tmp_path / "empty")}) is None
    assert find_git({}) is None


def test_start_read_with_runs_the_same_command(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", f"{ECHO}\necho --\n/usr/bin/env")
    process = start_read_with(git, tmp_path, ["diff", "HEAD"], (), environ={"PATH": "/some/bin"})
    out, _ = process.communicate(timeout=5)
    assert process.returncode == 0
    args, _, env = out.decode().partition("--\n")
    assert tuple(args.splitlines()) == read_args(tmp_path, ["diff", "HEAD"])
    assert {"GIT_TERMINAL_PROMPT=0", "GIT_OPTIONAL_LOCKS=0"} <= set(env.splitlines())


def test_write_git_args(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", ECHO)
    out = write_git(git, tmp_path, ["worktree", "add", "x"], timeout=5, environ={})
    assert out.splitlines() == [
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(tmp_path),
        "worktree",
        "add",
        "x",
    ]


def test_main_repo_of_a_repo_and_its_subfolder(git_repo: GitRepo) -> None:
    sub = git_repo.path / "a/b"
    sub.mkdir(parents=True)
    assert main_repo_of(git_repo.path) == git_repo.path
    assert main_repo_of(sub) == git_repo.path


def test_main_repo_of_a_linked_worktree(git_repo: GitRepo, tmp_path: Path) -> None:
    worktree = tmp_path / "feat"
    git_repo.git("worktree", "add", "--quiet", "-b", "feat", str(worktree))
    (worktree / "src").mkdir()
    assert main_repo_of(worktree) == git_repo.path
    assert main_repo_of(worktree / "src") == git_repo.path


def test_main_repo_of_outside_git(tmp_path: Path) -> None:
    folder = tmp_path / "plain"
    folder.mkdir()
    assert main_repo_of(folder) is None


def test_main_repo_of_a_git_file_pointing_elsewhere(git_repo: GitRepo) -> None:
    submodule = git_repo.path / "sub"
    (git_repo.path / ".git/modules/sub").mkdir(parents=True)
    submodule.mkdir()
    (submodule / ".git").write_text("gitdir: ../.git/modules/sub\n")
    assert main_repo_of(submodule) is None


def test_git_repo_has_one_commit_on_main(git_repo: GitRepo, tmp_path: Path) -> None:
    assert git_repo.git("log", "--format=%an %s").splitlines() == ["Test Author init"]
    assert git_repo.git("branch", "--show-current") == "main\n"
    assert git_env(tmp_path)["GIT_CONFIG_GLOBAL"] == "/dev/null"
    done = subprocess.run(
        ["git", "config", "--list", "--show-origin"],  # noqa: S607 — the test git
        cwd=git_repo.path,
        env=dict(git_repo.env),
        capture_output=True,
        text=True,
        check=True,
    )
    assert all(line.startswith("file:.git/config") for line in done.stdout.splitlines())
