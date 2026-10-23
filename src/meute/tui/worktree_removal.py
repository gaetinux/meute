"""`W` on the Sessions tab: what to check, then one or two confirmations before removing."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol, assert_never

from meute.core.board_view import BoardData, LaunchEntry, RemoveWorktree, SessionEntry
from meute.core.git_folder import git_folder
from meute.core.paths import shown_path
from meute.core.session_state import is_live
from meute.core.text import printable
from meute.core.worktrees import WorktreeCheck, listed_text
from meute.tui.board_types import BoardGit

STOP_FIRST = "stop the session first"
NO_GIT = "git not available"


@dataclass(frozen=True, slots=True)
class Idle:
    """No removal is being confirmed."""


@dataclass(frozen=True, slots=True)
class Asking:
    """The first question about `check`, its folder shown as `shown`."""

    check: WorktreeCheck
    shown: str


@dataclass(frozen=True, slots=True)
class Listing:
    """The changes and commits `check` would lose, then the second question."""

    check: WorktreeCheck


RemovalState = Idle | Asking | Listing


class WorktreeWorkers(Protocol):
    """Where `W` runs its slow steps: the check and the removal, each off the app's thread."""

    def check_worktree(
        self,
        folder: Path,
        shown: str,
        inspect: Callable[[Path], WorktreeCheck | str],
        ended: Callable[[WorktreeCheck | str], None],
    ) -> None:
        """Run `inspect` on `folder`, then give `ended` its result; `shown` names it meanwhile."""
        ...

    def is_removing(self, path: Path) -> bool:
        """Whether the worktree `path` is being removed."""
        ...

    def remove_worktree(self, action: RemoveWorktree, path_text: str) -> None:
        """Run the removal; the footer names the worktree as `path_text`."""
        ...


class WorktreeRemoval:
    """The confirmation of `W`: `y` goes on, any other key cancels; the removal runs elsewhere."""

    def __init__(
        self,
        *,
        git: BoardGit | None,
        workers: WorktreeWorkers,
        notice: Callable[[str], None],
        asking: Callable[[], bool],
    ) -> None:
        """`asking` tells whether the tab already asks another question (a stop, a close)."""
        self._git = git
        self._workers = workers
        self._notice = notice
        self._asking = asking
        self._state: RemovalState = Idle()

    def ask(self, entry: LaunchEntry, data: BoardData) -> None:
        """`W` on `entry`: check its worktree off the app's thread, or say why it cannot go."""
        if not isinstance(entry, SessionEntry):
            return
        session = entry.row.session
        if is_live(session.state):
            self._notice(STOP_FIRST)
        elif self._git is None:
            self._notice(NO_GIT)
        else:
            folder = git_folder(session, data.metrics.get(session.id))
            ended = partial(self._checked, home=data.home)
            self._workers.check_worktree(
                folder, shown_path(folder, data.home), self._git.inspect, ended
            )

    def _checked(self, check: WorktreeCheck | str, *, home: Path | None) -> None:
        """The check is back: ask the first question, dropped while another one is pending."""
        if isinstance(check, str):
            self._notice(printable(check))
        elif (
            isinstance(self._state, Idle)
            and not self._asking()
            and not self._workers.is_removing(check.path)
        ):
            _ = self.start(check, shown_path(check.path, home))

    def answer(self, key: str, home: Path | None) -> None:
        """Apply `key` to the pending question, starting the removal once it is confirmed."""
        action = self.key(key)
        if action is not None:
            self._workers.remove_worktree(action, shown_path(action.path, home))

    def start(self, check: WorktreeCheck, shown: str) -> str:
        """Ask the first question about `check`; return the footer text."""
        state = Asking(check, shown)
        self._state = state
        return _question(state)

    def key(self, character: str) -> RemoveWorktree | None:
        """Answer the pending question; the removal to run once it is confirmed."""
        state, self._state = self._state, Idle()
        if character != "y":
            return None
        match state:
            case Idle():
                return None
            case Asking(check=check) if check.clean:
                return RemoveWorktree(repo=check.repo, path=check.path, force=False)
            case Asking():
                self._state = Listing(state.check)
                return None
            case Listing(check=check):
                return RemoveWorktree(repo=check.repo, path=check.path, force=True)
            case _:
                assert_never(state)

    def cancel(self) -> None:
        """Drop the pending question."""
        self._state = Idle()

    @property
    def active(self) -> bool:
        """Whether a question is pending."""
        return not isinstance(self._state, Idle)

    def footer(self) -> str | None:
        """The pending question, or `None` when nothing is asked."""
        state = self._state
        return None if isinstance(state, Idle) else _question(state)


def _question(state: Asking | Listing) -> str:
    """The footer text of a pending question."""
    match state:
        case Asking(check=check, shown=shown) if check.clean:
            kept = "" if check.branch is None else f" (branch {printable(check.branch)} is kept)"
            return f"remove worktree {shown}?{kept} y/n"
        case Asking(shown=shown):
            return f"{shown} has uncommitted changes or unpushed commits: y shows them, n cancels"
        case Listing(check=check):
            lines = (*listed_text(check.changes), *listed_text(check.commits))
            return "\n".join((*lines, "remove anyway? y/n"))
        case _:
            assert_never(state)
