"""The launch form of the board asks its `BoardGit` for the worktrees of the repository."""

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from git_support import GitRepo
from meute.cli.board_git import CliBoardGit
from meute.core.board_view import BoardData, LaunchBash, LaunchClaude, SessionRow
from meute.core.project import RepoId
from meute.core.worktrees import Worktree, WorktreeCheck
from meute.tui.board import BoardApp, BoardOptions
from support import BOARD_HOME, BOARD_SESSION_A
from test_tui_board import FakeBackend, SnapCompare
from test_tui_launch_form import _MEUTE, _data  # pyright: ignore[reportPrivateUsage] — reused

Scenario = Callable[[BoardApp, Pilot[None]], Awaitable[None]]
_NO_POLL = 3600.0
_SIZE = (72, 30)
_OTHER = BOARD_HOME / "git" / "meute-wt"
_LISTED = Worktree(path=_OTHER, branch="feat/x", head="a" * 40, locked=False)


class FakeGit:
    """Answers `worktrees` with `answer`, and records the repositories it was asked about."""

    def __init__(self, answer: tuple[Worktree, ...] | str = ()) -> None:
        self.answer = answer
        self.asked: list[Path] = []

    def worktrees(self, repo: Path) -> tuple[Worktree, ...] | str:
        self.asked.append(repo)
        return self.answer

    def inspect(self, folder: Path) -> WorktreeCheck | str:
        raise NotImplementedError


def _busy_data() -> BoardData:
    """The repository `meute` has a live session in its folder."""
    session = replace(BOARD_SESSION_A, repo_id=RepoId(1))
    data = _data()
    return replace(data, sessions=(SessionRow(session=session, has_pane=True, displayed=True),))


def _text(app: BoardApp) -> str:
    content = app.query_one("#launch-form", Static).content
    assert isinstance(content, Content)
    return content.plain


def _run(
    backend: FakeBackend, git: FakeGit, scenario: Scenario, size: tuple[int, int] = _SIZE
) -> None:
    app = BoardApp(backend, BoardOptions(permission_mode="auto"), poll_seconds=_NO_POLL, git=git)

    async def run() -> None:
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(run())


def test_opening_on_a_busy_folder_shows_new_and_the_recommendation() -> None:
    git = FakeGit()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N")
        shown = _text(app)
        assert "Worktree  ◂ new ▸" in shown
        assert "Branch" in shown
        assert "⚠ another live session works in this folder" in shown

    _run(FakeBackend(_busy_data()), git, scenario)
    assert git.asked == [_MEUTE]


def test_left_goes_back_to_none() -> None:
    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "tab", "tab", "left")
        shown = _text(app)
        assert "Worktree  ◂ none ▸" in shown
        assert "⚠ another live session works in this folder" in shown

    _run(FakeBackend(_busy_data()), FakeGit(), scenario)


def test_an_existing_worktree_can_be_chosen_and_launched() -> None:
    backend = FakeBackend(_data())

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "tab", "tab", "right", "right")
        assert "feat/x  ~/git/meute-wt" in _text(app)
        await pilot.press("enter")

    _run(backend, FakeGit((_LISTED,)), scenario)
    [action] = backend.actions
    assert isinstance(action, LaunchClaude)
    assert action.cwd == _OTHER
    assert action.new_branch is None


def test_a_typed_branch_is_launched_as_a_new_worktree() -> None:
    backend = FakeBackend(_data())

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "right", "tab", "tab", "right")  # Bash, Worktree: new
        await pilot.press("tab", "f", "i", "x")  # the Branch field
        assert "Branch    fix" in _text(app)
        await pilot.press("enter")

    _run(backend, FakeGit(), scenario)
    [action] = backend.actions
    assert isinstance(action, LaunchBash)
    assert action.new_branch == "fix"
    assert action.repo_id == RepoId(1)


def test_the_error_of_the_list_is_shown() -> None:
    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N")
        assert "git not found" in _text(app)

    _run(FakeBackend(_data()), FakeGit("git not found"), scenario)


def test_changing_the_repository_asks_again() -> None:
    git = FakeGit()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "tab", "right")
        assert "notes" in _text(app)

    _run(FakeBackend(_data()), git, scenario)
    assert [path.name for path in git.asked] == ["meute", "notes"]


def test_without_git_the_form_offers_none_and_new() -> None:
    app = BoardApp(
        FakeBackend(_data()), BoardOptions(permission_mode="auto"), poll_seconds=_NO_POLL
    )

    async def run() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.pause()
            await pilot.press("N", "tab", "tab", "right", "right")
            assert "Worktree  ◂ none ▸" in _text(app)

    asyncio.run(run())


def _snapshot(snap_compare: SnapCompare, width: int) -> bool:
    app = BoardApp(
        FakeBackend(_busy_data()),
        BoardOptions(permission_mode="auto"),
        poll_seconds=_NO_POLL,
        git=FakeGit((_LISTED,)),
    )
    return snap_compare(
        app, press=["N", "right", "tab", "tab", "tab", "f", "i", "x"], terminal_size=(width, 30)
    )


def test_form_worktree_72_columns(snap_compare: SnapCompare) -> None:
    assert _snapshot(snap_compare, 72)


def test_form_worktree_44_columns(snap_compare: SnapCompare) -> None:
    assert _snapshot(snap_compare, 44)


def test_cli_board_git_lists_the_linked_worktrees(git_repo: GitRepo, tmp_path: Path) -> None:
    other = tmp_path / "linked"
    git_repo.git("worktree", "add", "--quiet", str(other), "-b", "feat/y")
    listed = CliBoardGit(git_repo.env, tuple).worktrees(git_repo.path)
    assert isinstance(listed, tuple)
    assert [(w.path, w.branch) for w in listed] == [(other, "feat/y")]


def test_cli_board_git_says_git_not_found(tmp_path: Path) -> None:
    assert CliBoardGit({"PATH": str(tmp_path)}, tuple).worktrees(tmp_path) == "git not found"


def test_cli_board_git_shows_the_failure_of_git(tmp_path: Path) -> None:
    answer = CliBoardGit({"PATH": os.environ["PATH"]}, tuple).worktrees(tmp_path / "missing")
    assert isinstance(answer, str)
    assert answer
    assert answer != "git not found"
