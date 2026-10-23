"""`W` checks the worktree off the app's thread, and the footer says what runs meanwhile."""

import asyncio
import threading
from dataclasses import replace
from pathlib import Path

from textual.content import Content
from textual.widgets import Static

from meute.core.board_view import (
    BoardData,
    CloseOrphan,
    SessionRow,
    StopSession,
    confirm_stop_text,
)
from meute.core.orphans import confirm_close_text
from meute.core.worktrees import Worktree, WorktreeCheck
from meute.tui.board import BoardApp
from support import (
    BOARD_HOME,
    BOARD_ID_A,
    BOARD_ID_B,
    BlockingBackend,
    board_data,
    board_session,
    until,
)
from test_tui_board import FakeBackend

_SIZE = (60, 30)
_NO_POLL = 3600.0
_REPO = BOARD_HOME / "git" / "meute"
_TREE = BOARD_HOME / "git" / "meute.worktrees" / "feat"
_SHOWN = "~/git/meute.worktrees/feat"
_CLEAN = WorktreeCheck(path=_TREE, repo=_REPO, branch="feat", changes=(), commits=())
_CHECKING = f"checking worktree {_SHOWN}…"
_QUESTION = f"remove worktree {_SHOWN}? (branch feat is kept) y/n"


def _data() -> BoardData:
    session = board_session(BOARD_ID_A, "feat", _TREE, None, exited=True)
    row = SessionRow(session=session, has_pane=False, displayed=False)
    return replace(board_data(), sessions=(row,), repos=(), orphans=(), metrics={})


def _footer(app: BoardApp) -> str:
    content = app.query_one("#footer", Static).content
    assert isinstance(content, Content)
    return content.plain


class BlockingGit:
    """Answers `inspect` once `release` is set; notes each folder and the thread it ran on."""

    def __init__(self, answer: WorktreeCheck | str | Exception = _CLEAN) -> None:
        self.answer = answer
        self.asked: list[Path] = []
        self.threads: list[int] = []
        self.release = threading.Event()
        self.returned = threading.Event()

    def worktrees(self, repo: Path) -> tuple[Worktree, ...] | str:
        raise NotImplementedError

    def inspect(self, folder: Path) -> WorktreeCheck | str:
        self.asked.append(folder)
        self.threads.append(threading.get_ident())
        assert self.release.wait(timeout=10)
        self.returned.set()
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_the_check_runs_off_the_app_thread_and_says_so() -> None:
    git = BlockingGit()
    app = BoardApp(FakeBackend(_data()), poll_seconds=_NO_POLL, git=git)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e", "W")
            await until(pilot, lambda: _footer(app) == _CHECKING, "no checking text")
            git.release.set()
            await until(pilot, lambda: _footer(app) == _QUESTION, "the question never came")

    asyncio.run(scenario())
    assert git.threads != [threading.get_ident()]
    assert len(git.threads) == 1


def test_w_again_on_the_folder_being_checked_is_ignored() -> None:
    git = BlockingGit()
    app = BoardApp(FakeBackend(_data()), poll_seconds=_NO_POLL, git=git)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e", "W")
            await until(pilot, lambda: git.asked, "the check never started")
            await pilot.press("W")
            git.release.set()
            await until(pilot, lambda: _footer(app) == _QUESTION, "the question never came")

    asyncio.run(scenario())
    assert git.asked == [_TREE]


def test_a_refusal_found_off_thread_goes_to_the_footer() -> None:
    git = BlockingGit("the worktree is locked")
    git.release.set()
    app = BoardApp(FakeBackend(_data()), poll_seconds=_NO_POLL, git=git)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e", "W")
            await until(pilot, lambda: _footer(app) == "the worktree is locked", "no refusal")

    asyncio.run(scenario())


def test_a_refusal_reaches_the_footer_printable() -> None:
    git = BlockingGit("git: bad \x1b[31mred")
    git.release.set()
    app = BoardApp(FakeBackend(_data()), poll_seconds=_NO_POLL, git=git)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e", "W")
            await until(pilot, lambda: _footer(app) == "git: bad �[31mred", "not printable")

    asyncio.run(scenario())


def test_a_broken_check_shows_its_error() -> None:
    git = BlockingGit(RuntimeError("boom"))
    git.release.set()
    app = BoardApp(FakeBackend(_data()), poll_seconds=_NO_POLL, git=git)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e", "W")
            await until(pilot, lambda: _footer(app) == "boom", "no error shown")
            await pilot.press("W")  # the folder is no longer being checked
            await until(pilot, lambda: len(git.asked) == 2, "the second check never ran")

    asyncio.run(scenario())


def test_the_footer_says_removing_while_the_removal_runs() -> None:
    backend = BlockingBackend(_data())
    git = BlockingGit()
    git.release.set()
    app = BoardApp(backend, poll_seconds=_NO_POLL, git=git)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e", "W")
            await until(pilot, lambda: _footer(app) == _QUESTION, "the question never came")
            await pilot.press("y")
            await until(
                pilot, lambda: _footer(app) == f"removing worktree {_SHOWN}…", "no removing text"
            )
            backend.release.set()
            await until(pilot, lambda: _footer(app) == f"worktree removed: {_SHOWN}", "not removed")

    asyncio.run(scenario())


def _with_live() -> BoardData:
    """The ended worktree session, then a live one, then the orphan pane of `board_data`."""
    live = board_session(BOARD_ID_B, "live", BOARD_HOME / "git" / "notes", None, exited=False)
    rows = (*_data().sessions, SessionRow(session=live, has_pane=True, displayed=False))
    return replace(_data(), sessions=rows, orphans=board_data().orphans)


def _check_returns_during(keys: tuple[str, ...], question: str) -> FakeBackend:
    """`W` on the ended session, then `keys` asking `question`; the check returns; then `y`."""
    git = BlockingGit()
    backend = FakeBackend(_with_live())
    app = BoardApp(backend, poll_seconds=_NO_POLL, git=git)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e", "up", "W")
            await until(pilot, lambda: git.asked, "the check never started")
            await pilot.press(*keys)
            assert _footer(app) == question
            git.release.set()
            await until(pilot, git.returned.is_set, "the check never came back")
            await pilot.pause(0.2)  # its result reaches the app's thread
            assert _footer(app) == question  # the check is dropped: the question stays
            await pilot.press("y")
            await until(pilot, lambda: backend.actions, "the answer sent nothing")
            assert not _footer(app).startswith("remove worktree")
            await pilot.press("y")  # nothing left to answer
            await pilot.pause()

    asyncio.run(scenario())
    return backend


def test_a_check_back_during_a_stop_question_never_hides_it() -> None:
    backend = _check_returns_during(("down", "x"), confirm_stop_text("live"))
    assert backend.actions == [StopSession(session_id=BOARD_ID_B)]


def test_a_check_back_during_a_close_question_never_hides_it() -> None:
    backend = _check_returns_during(("down", "down", "x"), confirm_close_text("claude"))
    assert [type(action) for action in backend.actions] == [CloseOrphan]
