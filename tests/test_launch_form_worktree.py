"""Tests for the Worktree and Branch fields of the launch form, and its recommendation."""

from dataclasses import replace
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from meute.core.board_view import BoardData, LaunchBash, LaunchClaude, RepoEntry
from meute.core.launch_form import (
    FormField,
    LaunchForm,
    choose,
    erase,
    form_action,
    move,
    open_form,
    shares_folder,
    type_text,
)
from meute.core.launch_form_view import form_lines
from meute.core.launch_form_worktree import (
    ExistingWorktree,
    NewWorktree,
    NoWorktree,
    cycle_worktree,
    with_worktrees,
)
from meute.core.repo import Repo
from meute.core.session import AgentKind
from meute.core.styled import Role, StyledLine, plain
from meute.core.worktrees import Worktree
from support import BOARD_AT, BOARD_HOME, BOARD_REPO_1, BOARD_REPO_2, board_data

_RECOMMENDATION = "⚠ another live session works in this folder: a new worktree is recommended"
_TRUST = "Claude will ask whether to trust the new folder"
_FIX = Worktree(
    path=BOARD_HOME / "git" / "meute.worktrees" / "fix",
    branch="fix",
    head="a1b2c3d4e5",
    locked=False,
    prunable=False,
)
_DETACHED = Worktree(
    path=Path("/srv/spike"), branch=None, head="0123456789ab", locked=False, prunable=False
)


def _open(
    repo: Repo | None = BOARD_REPO_1,
    worktrees: tuple[Worktree, ...] | str = (_FIX, _DETACHED),
    data: BoardData | None = None,
) -> LaunchForm:
    entry = None if repo is None else RepoEntry(repo=repo)
    return open_form(
        data or board_data(), entry, default_mode="auto", now=BOARD_AT, worktrees=worktrees
    )


def _tab_order(form: LaunchForm) -> list[FormField]:
    order = [form.field]
    for _ in range(len(FormField)):
        form = move(form, 1)
        if form.field is order[0]:
            break
        order.append(form.field)
    return order


def _texts(lines: list[StyledLine]) -> list[str]:
    return [plain(line) for line in lines]


def test_open_on_a_busy_repository_recommends_a_new_worktree() -> None:
    form = _open()
    assert form.worktree == NewWorktree()
    assert form.branch == ""
    assert not form.branch_typed
    assert form.worktrees == (_FIX, _DETACHED)
    assert form.worktrees_error is None


def test_open_on_a_free_repository_has_no_worktree() -> None:
    form = _open(BOARD_REPO_2)
    assert form.worktree == NoWorktree()


def test_open_without_a_repository_has_no_worktree_and_keeps_the_list_empty() -> None:
    form = _open(None, worktrees=())
    assert form.worktree == NoWorktree()
    assert FormField.WORKTREE not in _tab_order(form)


def test_a_failed_list_is_kept_as_the_error_of_the_field() -> None:
    form = _open(worktrees="git not found")
    assert form.worktrees == ()
    assert form.worktrees_error == "git not found"
    assert form.worktree == NewWorktree()


def test_tab_visits_worktree_after_repo_and_branch_instead_of_folder_with_new() -> None:
    assert _tab_order(_open()) == [
        FormField.TYPE,
        FormField.REPO,
        FormField.WORKTREE,
        FormField.BRANCH,
        FormField.TITLE,
        FormField.TASK,
        FormField.MODE,
    ]
    assert _tab_order(_open(BOARD_REPO_2)) == [
        FormField.TYPE,
        FormField.REPO,
        FormField.WORKTREE,
        FormField.FOLDER,
        FormField.TITLE,
        FormField.TASK,
        FormField.MODE,
    ]


def test_tab_skips_the_read_only_folder_of_an_existing_worktree() -> None:
    form = replace(_open(), worktree=ExistingWorktree(index=0), agent=AgentKind.BASH)
    assert _tab_order(form) == [
        FormField.TYPE,
        FormField.REPO,
        FormField.WORKTREE,
        FormField.TITLE,
    ]


def test_cycle_goes_none_new_then_the_existing_ones_and_wraps() -> None:
    form = replace(_open(), worktree=NoWorktree(), error="old")
    seen: list[object] = []
    for _ in range(5):
        form = cycle_worktree(form, 1)
        seen.append(form.worktree)
    assert seen == [
        NewWorktree(),
        ExistingWorktree(index=0),
        ExistingWorktree(index=1),
        NoWorktree(),
        NewWorktree(),
    ]
    assert form.error is None
    assert cycle_worktree(replace(form, worktree=NoWorktree()), -1).worktree == (
        ExistingWorktree(index=1)
    )


def test_cycle_without_a_list_offers_only_none_and_new() -> None:
    form = _open(worktrees="git not found")
    assert cycle_worktree(form, 1).worktree == NoWorktree()
    assert cycle_worktree(form, -1).worktree == NoWorktree()


def test_cycle_without_a_repository_changes_nothing() -> None:
    form = _open(None, worktrees=())
    assert cycle_worktree(form, 1) == form


def test_left_and_right_on_the_worktree_field_cycle_it() -> None:
    form = replace(_open(), field=FormField.WORKTREE)
    assert choose(form, -1, board_data(), BOARD_AT).worktree == NoWorktree()
    assert choose(form, 1, board_data(), BOARD_AT).worktree == ExistingWorktree(index=0)


def test_the_title_fills_the_branch_until_the_branch_is_typed() -> None:
    form = replace(_open(), field=FormField.TITLE)
    form = type_text(form, "Fix the Login bug!")
    assert form.branch == "fix-the-login-bug"
    form = erase(form)
    assert form.branch == "fix-the-login-bug"
    form = type_text(replace(form, field=FormField.BRANCH), "-2")
    assert (form.branch, form.branch_typed) == ("fix-the-login-bug-2", True)
    form = type_text(replace(form, field=FormField.TITLE), " now")
    assert form.branch == "fix-the-login-bug-2"


def test_erasing_the_branch_counts_as_typing_it() -> None:
    form = replace(_open(), field=FormField.BRANCH, branch="abc")
    form = erase(form)
    assert (form.branch, form.branch_typed) == ("ab", True)


def test_changing_repository_resets_the_choice_then_recommends_for_a_busy_folder() -> None:
    form = replace(_open(), worktree=ExistingWorktree(index=1), field=FormField.REPO)
    to_notes = choose(form, 1, board_data(), BOARD_AT)
    assert to_notes.repos[to_notes.repo or 0] == BOARD_REPO_2
    assert (to_notes.worktree, to_notes.worktrees) == (NoWorktree(), ())
    back = choose(choose(to_notes, 1, board_data(), BOARD_AT), 1, board_data(), BOARD_AT)
    assert back.repos[back.repo or 0] == BOARD_REPO_1
    assert back.worktree == NewWorktree()


def test_with_worktrees_takes_the_list_of_the_new_repository() -> None:
    form = replace(_open(BOARD_REPO_2), worktree=NewWorktree(), worktrees_error="old")
    taken = with_worktrees(form, (_DETACHED,))
    assert (taken.worktree, taken.worktrees, taken.worktrees_error) == (
        NoWorktree(),
        (_DETACHED,),
        None,
    )
    failed = with_worktrees(_open(), "git timed out after 2 s")
    assert (failed.worktree, failed.worktrees, failed.worktrees_error) == (
        NewWorktree(),
        (),
        "git timed out after 2 s",
    )


def test_a_new_worktree_launches_in_its_computed_folder_on_its_branch() -> None:
    form = replace(_open(), branch="  feat/x ", title="Feat")
    action = form_action(form, BOARD_HOME)
    assert isinstance(action, LaunchClaude)
    assert action.cwd == BOARD_HOME / "git" / "meute.worktrees" / "feat" / "x"
    assert action.new_branch == "feat/x"
    assert action.repo_id == BOARD_REPO_1.id
    bash = form_action(replace(form, agent=AgentKind.BASH), BOARD_HOME)
    assert bash == LaunchBash(
        cwd=action.cwd, repo_id=BOARD_REPO_1.id, title="Feat", new_branch="feat/x"
    )


@pytest.mark.parametrize(
    ("branch", "error"),
    [("   ", "branch is empty"), ("a..b", "invalid branch name: a..b")],
)
def test_a_refused_branch_is_the_error(branch: str, error: str) -> None:
    assert form_action(replace(_open(), branch=branch), BOARD_HOME) == error


def test_an_existing_worktree_launches_in_its_folder() -> None:
    form = replace(_open(), worktree=ExistingWorktree(index=0), folder="relative")
    action = form_action(form, BOARD_HOME)
    assert isinstance(action, LaunchClaude)
    assert (action.cwd, action.new_branch) == (_FIX.path, None)


def test_no_worktree_launches_in_the_typed_folder() -> None:
    form = replace(_open(), worktree=NoWorktree(), folder="~/git/meute/src")
    action = form_action(form, BOARD_HOME)
    assert isinstance(action, LaunchClaude)
    assert (action.cwd, action.new_branch) == (BOARD_HOME / "git" / "meute" / "src", None)


def test_without_a_repository_a_leftover_new_choice_launches_in_the_folder() -> None:
    form = replace(_open(), repo=None, folder="/srv/work")
    action = form_action(form, BOARD_HOME)
    assert isinstance(action, LaunchClaude)
    assert (action.cwd, action.new_branch, action.repo_id) == (Path("/srv/work"), None, None)


def test_shares_folder_follows_the_chosen_worktree() -> None:
    form = replace(_open(), branch="fix", busy=frozenset({_FIX.path, BOARD_REPO_1.path}))
    assert shares_folder(form, BOARD_HOME)
    assert shares_folder(replace(form, worktree=ExistingWorktree(index=0)), BOARD_HOME)
    assert not shares_folder(replace(form, worktree=ExistingWorktree(index=1)), BOARD_HOME)
    assert shares_folder(replace(form, branch="other"), BOARD_HOME)  # `new`: the repository folder
    assert shares_folder(replace(form, branch=""), BOARD_HOME)
    free = replace(form, busy=frozenset({_FIX.path}))
    assert not shares_folder(free, BOARD_HOME)  # `new`, the repository folder is not busy
    assert shares_folder(replace(form, worktree=NoWorktree()), BOARD_HOME)


def test_claude_form_with_a_new_worktree(snapshot: SnapshotAssertion) -> None:
    form = replace(_open(), field=FormField.BRANCH, branch="fix-login", title="Fix login")
    assert _texts(form_lines(form, home=BOARD_HOME, width=80)) == snapshot


def test_bash_form_with_a_new_worktree_has_no_trust_note(snapshot: SnapshotAssertion) -> None:
    form = replace(_open(), agent=AgentKind.BASH, branch="fix-login")
    lines = _texts(form_lines(form, home=BOARD_HOME, width=80))
    assert _TRUST not in lines
    assert lines == snapshot


def test_form_on_an_existing_worktree(snapshot: SnapshotAssertion) -> None:
    form = replace(_open(), worktree=ExistingWorktree(index=0), agent=AgentKind.BASH)
    assert _texts(form_lines(form, home=BOARD_HOME, width=80)) == snapshot
    detached = replace(form, worktree=ExistingWorktree(index=1))
    assert _texts(form_lines(detached, home=BOARD_HOME, width=80)) == snapshot


def test_form_with_a_failed_list(snapshot: SnapshotAssertion) -> None:
    form = replace(_open(BOARD_REPO_2, worktrees="git not found"), agent=AgentKind.BASH)
    assert _texts(form_lines(form, home=BOARD_HOME, width=80)) == snapshot


@pytest.mark.parametrize("width", [40, 12])
def test_a_narrow_form_with_a_new_worktree(width: int, snapshot: SnapshotAssertion) -> None:
    form = replace(_open(), branch="a-rather-long-branch-name", title="Long")
    lines = form_lines(form, home=BOARD_HOME, width=width)
    assert all(len(plain(line)) <= width for line in lines)
    assert _texts(lines) == snapshot


def test_without_a_repository_the_worktree_field_is_hidden() -> None:
    lines = _texts(form_lines(_open(None, worktrees=()), home=BOARD_HOME, width=80))
    assert not any(line.startswith(("Worktree", "Branch")) for line in lines)


def test_roles_of_the_worktree_lines() -> None:
    form = replace(_open(worktrees="git not found"), field=FormField.WORKTREE, branch="x")
    rows = {plain(line).strip(): line for line in form_lines(form, home=BOARD_HOME, width=80)}
    worktree = next(line for text, line in rows.items() if text.startswith("Worktree"))
    assert worktree[0].role is Role.TITLE
    assert rows["git not found"][-1].role is Role.DIM
    assert rows[_TRUST][-1].role is Role.DIM
    busy = form_lines(replace(form, worktree=NoWorktree()), home=BOARD_HOME, width=80)
    warning = next(line for line in busy if plain(line) == _RECOMMENDATION)
    assert warning[0].role is Role.WARN


def test_the_recommendation_stays_while_the_chosen_folder_is_busy() -> None:
    form = replace(_open(), worktree=NoWorktree())
    assert _RECOMMENDATION in _texts(form_lines(form, home=BOARD_HOME, width=80))
    free = replace(form, folder="/elsewhere")
    assert _RECOMMENDATION not in _texts(form_lines(free, home=BOARD_HOME, width=80))
