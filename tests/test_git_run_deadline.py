"""`read_git` gives its filter lookup and its command one shared deadline."""

import time
from pathlib import Path

import pytest

from git_support import fake_git
from meute.git import run
from meute.git.run import GitError, read_git

SLOW_STEPS = """case "$*" in
  *" config "*) sleep 0.6; exit 1 ;;
  *) sleep 0.6; echo done ;;
esac"""


def test_the_lookup_and_the_command_share_one_deadline(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", SLOW_STEPS)
    started = time.monotonic()
    with pytest.raises(GitError) as caught:
        read_git(git, tmp_path, ["status"], timeout=1, environ={})
    assert str(caught.value) == "git timed out after 1 s"  # the timeout given, not what was left
    assert time.monotonic() - started < 1.5


def test_both_steps_within_the_deadline_succeed(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", SLOW_STEPS)
    assert read_git(git, tmp_path, ["status"], timeout=3, environ={}) == "done\n"


def test_no_time_left_after_the_lookup_starts_no_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git = tmp_path / "nowhere/git"  # starting the command would say `git not found`

    def slow_lookup(*_: object, **__: object) -> tuple[str, ...]:
        time.sleep(0.2)  # finished, but past the deadline
        return ()

    monkeypatch.setattr(run, "filter_drivers", slow_lookup)
    with pytest.raises(GitError) as caught:
        read_git(git, tmp_path, ["status"], timeout=0.1, environ={})
    assert str(caught.value) == "git timed out after 0.1 s"
