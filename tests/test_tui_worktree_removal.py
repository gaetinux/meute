"""`W` removes the linked worktree of an ended session, after one or two confirmations."""

import asyncio
import threading
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_view import FOOTER, KEYS_HELP, BoardData, RemoveWorktree, SessionRow
from meute.core.errors import MeuteError
from meute.core.statusline import StatuslineData
from meute.core.worktrees import Worktree, WorktreeCheck
from meute.tui.board import BoardApp
from support import BOARD_HOME, BOARD_ID_A, BlockingBackend, board_data, board_session, until
from test_tui_board import FakeBackend, SnapCompare

Scenario = Callable[[BoardApp, Pilot[None]], Awaitable[None]]
_SIZE = (60, 30)
_NO_POLL = 3600.0
_REPO = BOARD_HOME / "git" / "meute"
_TREE = BOARD_HOME / "git" / "meute.worktrees" / "feat"
_SHOWN = "~/git/meute.worktrees/feat"
_CLEAN = WorktreeCheck(path=_TREE, repo=_REPO, branch="feat", locked=False, changes=(), commits=())
_DIRTY = replace(
    _CLEAN,
    changes=tuple(f" M file{n}.py" for n in range(12)),
    commits=("abc1234 add the parser", "def5678 fix the parser"),
)
_ASK_DIRTY = f"{_SHOWN} has uncommitted changes or unpushed commits: y shows them, n cancels"
_LISTED = "\n".join(
    (
        *(f" M file{n}.py" for n in range(10)),
        "… and 2 more",
        "abc1234 add the parser",
        "def5678 fix the parser",
        "remove anyway? y/n",
    )
)


class FakeGit:
    """Answers `inspect` with `answer`, and records the folders it was asked about."""

    def __init__(self, answer: WorktreeCheck | str) -> None:
        self.answer = answer
        self.asked: list[Path] = []

    def worktrees(self, repo: Path) -> tuple[Worktree, ...] | str:
        raise NotImplementedError

    def inspect(self, folder: Path) -> WorktreeCheck | str:
        self.asked.append(folder)
        return self.answer


def _data(*, exited: bool = True, metrics: StatuslineData | None = None) -> BoardData:
    session = board_session(BOARD_ID_A, "feat", _TREE, None, exited=exited)
    return replace(
        board_data(),
        sessions=(SessionRow(session=session, has_pane=False, displayed=False),),
        repos=(),
        orphans=(),
        metrics={} if metrics is None else {BOARD_ID_A: metrics},
    )


def _footer(app: BoardApp) -> str:
    content = app.query_one("#footer", Static).content
    assert isinstance(content, Content)
    return content.plain


def _removed(app: BoardApp) -> bool:
    return _footer(app).startswith("worktree removed")


def _footers(
    git: FakeGit | None, *keys: str, data: BoardData | None = None
) -> tuple[list[str], FakeBackend]:
    """Press `e` then each key on a fresh board; the footer after each key, and the backend."""
    backend = FakeBackend(_data() if data is None else data)
    app = BoardApp(backend, poll_seconds=_NO_POLL, git=git)
    footers: list[str] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e")
            for key in keys:
                await pilot.press(key)
                footers.append(_footer(app))
            if any(isinstance(action, RemoveWorktree) for action in backend.actions):
                await until(pilot, lambda: _removed(app), "the removal never ended")
            footers.append(_footer(app))

    asyncio.run(scenario())
    return footers, backend


def test_w_on_a_live_session_asks_to_stop_it_first() -> None:
    git = FakeGit(_CLEAN)
    footers, backend = _footers(git, "W", data=_data(exited=False))
    assert footers[0] == "stop the session first"
    assert git.asked == []
    assert backend.actions == []


def test_w_without_git_says_git_is_not_available() -> None:
    footers, backend = _footers(None, "W")
    assert footers[0] == "git not available"
    assert backend.actions == []


def test_each_refusal_of_inspect_goes_to_the_footer() -> None:
    for refusal in (
        f"not a linked worktree: {_TREE}",
        "a live session works in this worktree",
        "the worktree is locked",
        f"folder not found: {_TREE}",
        "git not found",
    ):
        footers, backend = _footers(FakeGit(refusal), "W", "y")
        assert footers[0] == refusal
        assert footers[1] == FOOTER  # `y` after a refusal confirms nothing
        assert backend.actions == []


def test_w_inspects_the_worktree_claude_reported() -> None:
    other = BOARD_HOME / "git" / "meute" / ".claude" / "worktrees" / "x"
    git = FakeGit(_CLEAN)
    _ = _footers(git, "W", data=_data(metrics=StatuslineData(worktree_path=str(other))))
    assert git.asked == [other]


def test_w_inspects_the_session_folder_without_a_reported_worktree() -> None:
    git = FakeGit(_CLEAN)
    _ = _footers(git, "W")
    assert git.asked == [_TREE]


def test_a_clean_worktree_is_removed_after_one_y() -> None:
    footers, backend = _footers(FakeGit(_CLEAN), "W", "y")
    assert footers[0] == f"remove worktree {_SHOWN}? (branch feat is kept) y/n"
    assert backend.actions == [RemoveWorktree(repo=_REPO, path=_TREE, force=False)]
    assert footers[-1] == f"worktree removed: {_SHOWN}"


def test_a_detached_clean_worktree_names_no_branch() -> None:
    footers, _ = _footers(FakeGit(replace(_CLEAN, branch=None)), "W", "n")
    assert footers[0] == f"remove worktree {_SHOWN}? y/n"


def test_a_clean_worktree_kept_on_any_other_key() -> None:
    footers, backend = _footers(FakeGit(_CLEAN), "W", "n")
    assert footers[1] == FOOTER
    assert backend.actions == []


def test_a_dirty_worktree_lists_then_asks_then_forces() -> None:
    footers, backend = _footers(FakeGit(_DIRTY), "W", "y", "y")
    assert footers[0] == _ASK_DIRTY
    assert footers[1] == _LISTED
    assert backend.actions == [RemoveWorktree(repo=_REPO, path=_TREE, force=True)]
    assert footers[-1] == f"worktree removed: {_SHOWN}"


def test_a_dirty_worktree_is_kept_when_the_first_question_is_declined() -> None:
    footers, backend = _footers(FakeGit(_DIRTY), "W", "n", "y")
    assert footers[1] == FOOTER
    assert footers[2] == FOOTER  # the later `y` no longer answers anything
    assert backend.actions == []


def test_a_dirty_worktree_is_kept_when_the_list_is_declined() -> None:
    footers, backend = _footers(FakeGit(_DIRTY), "W", "y", "x", "y")
    assert footers[2] == FOOTER
    assert footers[3] == FOOTER
    assert backend.actions == []


def test_no_force_before_the_second_confirmation() -> None:
    _, backend = _footers(FakeGit(_DIRTY), "W", "y")
    assert backend.actions == []


def test_a_failed_removal_shows_the_error() -> None:
    backend = BlockingBackend(_data())
    backend.perform_error = MeuteError("git: fatal: cannot remove")
    backend.release.set()
    app = BoardApp(backend, poll_seconds=_NO_POLL, git=FakeGit(_CLEAN))

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e", "W", "y")
            await until(pilot, lambda: "cannot remove" in _footer(app), "no error shown")

    asyncio.run(scenario())
    assert backend.threads != [threading.get_ident()]


def test_w_again_while_removing_sends_one_action() -> None:
    backend = BlockingBackend(_data())
    app = BoardApp(backend, poll_seconds=_NO_POLL, git=FakeGit(_CLEAN))

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e", "W", "y")
            await until(pilot, lambda: backend.actions, "the removal never started")
            await pilot.press("W", "y")
            backend.release.set()
            await until(pilot, lambda: "worktree removed" in _footer(app), "never removed")

    asyncio.run(scenario())
    assert len(backend.actions) == 1


def test_the_keys_help_tells_what_w_does() -> None:
    lines = KEYS_HELP.splitlines()
    assert lines[lines.index("r resume an ended Claude session") + 1] == (
        "W remove the worktree of an ended session"
    )
    assert all(len(line) <= 58 for line in lines)


def test_worktree_list_44_columns(snap_compare: SnapCompare) -> None:
    app = BoardApp(FakeBackend(_data()), poll_seconds=_NO_POLL, git=FakeGit(_DIRTY))
    assert snap_compare(app, press=["e", "W", "y"], terminal_size=(44, 30))


def test_a_click_cancels_the_removal() -> None:
    backend = FakeBackend(_data())
    app = BoardApp(backend, poll_seconds=_NO_POLL, git=FakeGit(_CLEAN))

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e", "W")
            _ = await pilot.click("#board", offset=(2, 0))
            assert _footer(app) == FOOTER
            await pilot.press("y")

    asyncio.run(scenario())
    assert backend.actions == []
