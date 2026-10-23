"""Tests that kill the mutants plan 6a left alive (docs/dev/mutants/2026-plan-6a-python.md)."""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from git_support import GitRepo, fake_git, git_env, make_repo, real_git
from meute.core.board_sessions import board_sessions
from meute.core.board_view import BoardData, RepoEntry
from meute.core.git_state import GitState, parse_numstat, parse_status_v2
from meute.core.launch_form import FormField, erase, open_form, type_text
from meute.core.sessions_view import ViewState
from meute.core.statusline import StatuslineData
from meute.git import run, worktree
from meute.git.run import (
    GitError,
    filter_names,
    has_exited,
    kill_read,
    read_git,
    start_read,
    start_read_with,
    write_git,
)
from support import BOARD_AT, BOARD_REPO_1, BOARD_SESSION_A, board_data

_HEAD = "# branch.oid 0123456789abcdef\n# branch.head main\n"
_NO_LOOKUP = 'case "$*" in *--get-regexp*) exit 1;; esac'  # no filter driver configured
_SLOW = f"{_NO_LOOKUP}\nsleep 3"


# --- meute.core.launch_form


def test_editing_the_branch_clears_the_error() -> None:
    form = open_form(board_data(), RepoEntry(repo=BOARD_REPO_1), default_mode="auto", now=BOARD_AT)
    form = replace(form, field=FormField.BRANCH, branch="ab", error="branch is empty")
    assert type_text(form, "x").error is None
    assert erase(form).error is None


# --- meute.core.board_sessions


def test_a_card_takes_the_git_state_of_the_worktree_claude_reported() -> None:
    state = GitState(branch="wt", detached=None, upstream=False, ahead=0, behind=0, dirty=False)
    data: BoardData = replace(
        board_data(),
        metrics={BOARD_SESSION_A.id: StatuslineData(worktree_path="/srv/wt")},
        git={Path("/srv/wt"): state, BOARD_SESSION_A.cwd: replace(state, branch="main")},
    )
    assert board_sessions(data, ViewState()).infos[BOARD_SESSION_A.id].git == state


# --- meute.core.git_state


def test_blank_lines_and_unknown_headers_are_not_changes() -> None:
    state = parse_status_v2(_HEAD + "\n   \n# stash 3\n")
    assert state is not None
    assert not state.dirty


@pytest.mark.parametrize("ab", ["+1 +2", "-1 -2", "+1 -2 -3", "nonsense"])
def test_a_malformed_ahead_behind_counts_nothing(ab: str) -> None:
    state = parse_status_v2(_HEAD + "# branch.upstream origin/main\n# branch.ab " + ab + "\n")
    assert state is not None
    assert (state.ahead, state.behind) == (0, 0)


def test_eighteen_digits_still_count() -> None:
    state = parse_status_v2(_HEAD + "# branch.ab +123456789012345678 -0\n")
    assert state is not None
    assert state.ahead == 123456789012345678


def test_numstat_columns_are_split_on_the_first_two_tabs_only() -> None:
    assert parse_numstat("1 2 spaces-are-not-tabs\n") == (0, 0)
    assert parse_numstat("1\t2\tpath\twith\ttabs\n") == (1, 2)


# --- meute.git.run


def test_a_filter_key_without_a_name_does_not_stop_the_lookup() -> None:
    assert filter_names("filter.clean\nx\0filter.lfs.clean\ny\0") == ("lfs",)


def test_a_filter_value_on_several_lines_keeps_its_name() -> None:
    assert filter_names("filter.f.clean\nrun.sh\nsecond.line\0") == ("f",)


def test_git_reads_nothing_from_our_stdin(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", "readlink /proc/self/fd/0")
    process = start_read_with(git, tmp_path, ["status"], (), environ={})
    out, _ = process.communicate(timeout=5)
    assert out.decode().strip() == os.devnull


def test_a_git_that_cannot_run_names_the_reason(tmp_path: Path) -> None:
    git = tmp_path / "git"
    git.write_text("#!/bin/sh\n")
    git.chmod(0o644)
    with pytest.raises(GitError) as caught:
        read_git(git, tmp_path, ["status"], timeout=5, environ={})
    assert str(caught.value) == "git: Permission denied"


def test_a_git_reaped_elsewhere_has_exited(tmp_path: Path) -> None:
    process = start_read_with(fake_git(tmp_path / "bin", "exit 0"), tmp_path, ["x"], (), environ={})
    _ = os.waitpid(process.pid, 0)
    assert has_exited(process)


def test_killing_a_finished_git_returns_its_status(tmp_path: Path) -> None:
    process = start_read_with(fake_git(tmp_path / "bin", "exit 4"), tmp_path, ["x"], (), environ={})
    assert process.wait(timeout=5) == 4
    assert kill_read(process) == 4


def test_a_message_that_is_not_utf8_is_shown(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", f"{_NO_LOOKUP}\nprintf '\\377oops\\n' >&2\nexit 2")
    with pytest.raises(GitError) as caught:
        read_git(git, tmp_path, ["status"], timeout=5, environ={})
    assert str(caught.value) == "git: �oops"


def test_a_silent_failure_after_the_lookup_gives_the_status(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", f"{_NO_LOOKUP}\nexit 4")
    with pytest.raises(GitError) as caught:
        read_git(git, tmp_path, ["status"], timeout=5, environ={})
    assert str(caught.value) == "git: exit status 4"


def test_reads_and_writes_time_out_after_the_lookup(tmp_path: Path) -> None:
    git = fake_git(tmp_path / "bin", _SLOW)
    for call in (read_git, write_git):
        with pytest.raises(GitError) as caught:
            call(git, tmp_path, ["status"], timeout=0.3, environ={})
        assert str(caught.value) == "git timed out after 0.3 s"


def test_the_lookup_of_start_read_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "_LOOKUP_TIMEOUT", 0.3)
    git = fake_git(tmp_path / "bin", "sleep 3")
    with pytest.raises(GitError) as caught:
        start_read(git, tmp_path, ["status"], environ={})
    assert str(caught.value) == "git timed out after 0.3 s"


# --- meute.git.worktree


def test_every_worktree_command_has_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("CHECK_TIMEOUT", "ADD_TIMEOUT", "REMOVE_TIMEOUT"):
        monkeypatch.setattr(worktree, name, 0.3)
    git = fake_git(tmp_path / "bin", _SLOW)
    calls = [
        lambda: worktree.list_worktrees_text(git, tmp_path, timeout=0.3, environ={}),
        lambda: worktree.check_branch(git, tmp_path, "x", environ={}),
        lambda: worktree.add_worktree(git, tmp_path, tmp_path / "w", "x", environ={}),
        lambda: worktree.worktree_changes(git, tmp_path, environ={}),
        lambda: worktree.worktree_only_commits(git, tmp_path, "x", environ={}),
        lambda: worktree.oneline_log(git, tmp_path, ("abc",), environ={}),
        lambda: worktree.remove_worktree(git, tmp_path, tmp_path / "w", force=False, environ={}),
    ]
    for call in calls:
        with pytest.raises(GitError) as caught:
            call()
        assert str(caught.value) == "git timed out after 0.3 s"


def test_check_branch_refuses_an_invalid_name(git_repo: GitRepo) -> None:
    with pytest.raises(GitError) as caught:
        worktree.check_branch(real_git(git_repo), git_repo.path, "a..b", environ=git_repo.env)
    assert str(caught.value) == "git: fatal: 'a..b' is not a valid branch name"


def test_a_detached_head_excludes_no_branch_even_one_named_none(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo", git_env(tmp_path))
    repo.git("checkout", "--quiet", "--detach")
    (repo.path / "README.md").write_text("detached\n")
    repo.git("commit", "--quiet", "--all", "--message=detached")
    repo.git("branch", "None")  # the commit is also on a branch: it is not the worktree's own
    git = real_git(repo)
    assert worktree.worktree_only_commits(git, repo.path, None, environ=repo.env) == ()
