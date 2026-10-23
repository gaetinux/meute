"""Tests of the pure worktree model (list outputs captured from real git, frozen)."""

import os
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from meute.core.worktrees import (
    Worktree,
    WorktreeCheck,
    branch_error,
    branch_from_title,
    listed_text,
    parse_worktree_list,
    worktree_path,
)

OID = "a8aa3468fa711e5772c0d021972cb1006f3767f1"
MAIN = Path("/r/repo")

# `git worktree list --porcelain -z` (git 2.47.3) for a repository with seven linked worktrees.
REAL = (
    f"worktree /r/repo\0HEAD {OID}\0branch refs/heads/main\0\0"
    f"worktree /r/my wt\0HEAD {OID}\0branch refs/heads/spaced\0\0"
    f"worktree /r/wt\nnl\0HEAD {OID}\0branch refs/heads/nl\0\0"
    f"worktree /r/wt-det\0HEAD {OID}\0detached\0\0"
    f"worktree /r/wt-feat\0HEAD {OID}\0branch refs/heads/feat/x\0\0"
    f"worktree /r/wt-gone\0HEAD {OID}\0branch refs/heads/gone\0"
    "prunable gitdir file points to non-existent location\0\0"
    f"worktree /r/wt-lock\0HEAD {OID}\0branch refs/heads/lk\0locked why\0\0"
    f"worktree /r/wt-lock2\0HEAD {OID}\0branch refs/heads/lk2\0locked two\nlines\0\0"
)
BARE = "worktree /r/bare.git\0bare\0\0"


def _wt(path: str, branch: str | None, *, locked: bool = False) -> Worktree:
    return Worktree(path=Path(path), branch=branch, head=OID, locked=locked)


def test_parse_real_output() -> None:
    assert parse_worktree_list(REAL, MAIN) == (
        _wt("/r/my wt", "spaced"),
        _wt("/r/wt\nnl", "nl"),
        _wt("/r/wt-det", None),
        _wt("/r/wt-feat", "feat/x"),
        _wt("/r/wt-lock", "lk", locked=True),
        _wt("/r/wt-lock2", "lk2", locked=True),
    )


def test_parse_locked_without_reason() -> None:
    text = (
        f"worktree /r/repo\0HEAD {OID}\0\0"
        f"worktree /r/a\0HEAD {OID}\0branch refs/heads/a\0locked\0\0"
    )
    assert parse_worktree_list(text, MAIN) == (_wt("/r/a", "a", locked=True),)


def test_parse_drops_first_block_even_when_not_main() -> None:
    text = f"worktree /r/other\0HEAD {OID}\0\0worktree /r/a\0HEAD {OID}\0branch refs/heads/a\0"
    assert parse_worktree_list(text, MAIN) == (_wt("/r/a", "a"),)


def test_parse_drops_main_path_and_relative_paths() -> None:
    text = (
        f"worktree /r/x\0HEAD {OID}\0\0"
        f"worktree /r/repo\0HEAD {OID}\0branch refs/heads/m\0\0"
        f"worktree rel/path\0HEAD {OID}\0branch refs/heads/r\0\0"
        f"worktree /r/ok\0HEAD {OID}\0branch refs/heads/ok\0\0"
    )
    assert parse_worktree_list(text, MAIN) == (_wt("/r/ok", "ok"),)


def test_parse_drops_bare_and_blocks_without_path() -> None:
    text = f"worktree /r/x\0HEAD {OID}\0\0{BARE}HEAD {OID}\0branch refs/heads/z\0\0"
    assert parse_worktree_list(text, MAIN) == ()


def test_parse_empty() -> None:
    assert parse_worktree_list("", MAIN) == ()


def test_parse_tolerates_extra_empty_fields_and_no_final_one() -> None:
    text = f"worktree /r/x\0HEAD {OID}\0\0\0\0worktree /r/a\0branch refs/heads/a"
    assert parse_worktree_list(text, MAIN) == (
        Worktree(path=Path("/r/a"), branch="a", head="", locked=False),
    )


def test_parse_keeps_newlines_inside_fields() -> None:
    text = "worktree /r/x\0\0worktree /r/a\nworktree /r/b\0branch refs/heads/a\nb\0\0"
    assert parse_worktree_list(text, MAIN) == (
        Worktree(path=Path("/r/a\nworktree /r/b"), branch="a\nb", head="", locked=False),
    )


@given(st.text())
def test_parse_never_raises(text: str) -> None:
    parse_worktree_list(text, MAIN)


def test_parse_huge_input() -> None:
    text = "worktree /r/x\0\0" + "worktree /r/a\0branch refs/heads/a\0\0" * 20000
    assert len(parse_worktree_list(text, MAIN)) == 20000


def test_branch_from_title_examples() -> None:
    assert branch_from_title("Fix login!") == "fix-login"
    assert branch_from_title("  ") == ""
    assert branch_from_title("Été 2026") == "t-2026"
    assert branch_from_title("feat/X Y") == "feat/x-y"


def test_branch_from_title_collapses_and_trims() -> None:
    assert branch_from_title("--a   b--") == "a-b"
    assert branch_from_title("./a.b/.") == "a.b"
    assert branch_from_title("a_b.c") == "a_b.c"


def test_branch_from_title_bounded() -> None:
    result = branch_from_title("ab " * 100)
    assert len(result) <= 60
    assert not result.endswith("-")


@given(st.text())
def test_branch_from_title_properties(title: str) -> None:
    result = branch_from_title(title)
    assert len(result) <= 60
    assert result == result.strip("-./")
    assert "--" not in result
    assert all(c.isascii() and (c.isalnum() or c in "-_./") for c in result)


def test_branch_error_rejects() -> None:
    for bad in ["-x", "--force", "a..b", "feat/", "a b", "a\nb", "../../etc", "x.lock",
                "", "/abs", "a//b", "a\\b", "a~b", "a^b", "a:b", "a?b", "a*b", "a[b",
                "a@{b", "a/./b", "a/..", ".", "a.", "a\x7fb", "a\tb"]:  # fmt: skip
        assert branch_error(bad) is not None, bad


def test_branch_error_messages() -> None:
    assert branch_error("") == "branch is empty"
    assert branch_error("-x") == "invalid branch name: -x"


def test_branch_error_accepts() -> None:
    for good in ["main", "feat/x-y", "a.b", "v1.0/rc_2", "x.lockfile"]:
        assert branch_error(good) is None, good


def test_worktree_path() -> None:
    assert worktree_path(Path("/r/repo"), "feat/x") == Path("/r/repo.worktrees/feat/x")


@given(st.text(max_size=40))
def test_accepted_branches_stay_under_worktrees_dir(branch: str) -> None:
    if branch_error(branch) is not None:
        return
    repo = Path("/r/repo")
    base = os.path.normpath(repo.parent / "repo.worktrees")
    assert os.path.normpath(worktree_path(repo, branch)).startswith(base + os.sep)


def _check(changes: tuple[str, ...], commits: tuple[str, ...]) -> WorktreeCheck:
    return WorktreeCheck(path=Path("/r/a"), repo=MAIN, branch="a", changes=changes, commits=commits)


def test_check_clean() -> None:
    assert _check((), ()).clean
    assert not _check((" M a",), ()).clean
    assert not _check((), ("abc x",)).clean


def test_listed_text() -> None:
    assert listed_text([]) == []
    ten = [f"l{i}" for i in range(10)]
    assert listed_text(ten) == ten
    assert listed_text([*ten, "l10"]) == [*ten, "… and 1 more"]
    assert listed_text(["a\x1b[31m"]) == ["a�[31m"]
    assert listed_text(ten, limit=3) == [*ten[:3], "… and 7 more"]
