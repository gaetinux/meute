"""The non-blocking pieces of a guarded read: lookup, read with known filters, exit and kill."""

import time
from pathlib import Path

import pytest

from git_support import fake_git
from meute.git.run import (
    GitError,
    has_exited,
    kill_read,
    lookup_filters,
    read_args,
    start_filter_lookup,
    start_read_with,
)
from support import wait_until
from test_git_run import is_alive

ECHO = 'for a in "$@"; do printf "%s\\n" "$a"; done'


def test_start_filter_lookup_runs_the_lookup(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", ECHO)
    process = start_filter_lookup(git, tmp_path, environ={})
    out, _ = process.communicate(timeout=5)
    expected = read_args(tmp_path, ["config", "--null", "--get-regexp", r"^filter\."])
    assert tuple(out.decode().splitlines()) == expected


def test_start_filter_lookup_does_not_wait(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", "sleep 30")
    started = time.monotonic()
    process = start_filter_lookup(git, tmp_path, environ={})
    assert time.monotonic() - started < 1
    assert not has_exited(process)
    assert kill_read(process) < 0
    assert process.stdout is not None
    assert process.stdout.closed


def test_start_read_with_neutralises_the_given_filters(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", ECHO)
    process = start_read_with(git, tmp_path, ["status"], ("x",), environ={})
    out, _ = process.communicate(timeout=5)
    assert tuple(out.decode().splitlines()) == read_args(tmp_path, ["status"], ("x",))


def test_start_read_with_missing_git(tmp_path: Path) -> None:
    with pytest.raises(GitError, match=r"^git not found$"):
        start_read_with(tmp_path / "nowhere/git", tmp_path, ["status"], (), environ={})


def test_lookup_filters_reads_a_finished_lookup() -> None:
    assert lookup_filters(1, b"", b"") == ()
    assert lookup_filters(0, b"filter.a.clean\ncat\0filter.b.smudge\ncat\0", b"") == ("a", "b")
    with pytest.raises(GitError, match=r"^git: boom$"):
        lookup_filters(128, b"", b"boom\n")
    with pytest.raises(GitError, match=r"^git: unsupported filter driver name$"):
        lookup_filters(0, b"filter.a=b.clean\ncat\0", b"")


def test_has_exited_leaves_git_to_reap(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", "exit 3")
    process = start_read_with(git, tmp_path, ["status"], (), environ={})
    wait_until("git to exit", lambda: has_exited(process))
    assert Path(f"/proc/{process.pid}").exists()  # a zombie: its group id is not reused
    assert kill_read(process) == 3
    assert not Path(f"/proc/{process.pid}").exists()


def test_kill_read_kills_the_whole_group(tmp_path: Path) -> None:
    pids = tmp_path / "pids"
    git = fake_git(tmp_path / "bin", f'sleep 30 &\necho $! > "{pids}"\nwait')
    process = start_read_with(git, tmp_path, ["status"], (), environ={})
    wait_until("the child to start", lambda: pids.exists() and pids.read_text().strip() != "")
    assert kill_read(process) < 0
    child = int(pids.read_text())
    wait_until("the child to die", lambda: not is_alive(child), timeout=3)
