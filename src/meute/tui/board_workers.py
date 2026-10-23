"""The board's slow actions, each in a thread worker: stopping a session, launching on a task."""

from collections.abc import Callable
from contextlib import suppress
from functools import partial
from pathlib import Path

from textual.app import App

from meute.core.board_view import (
    AdoptOrphan,
    BoardAction,
    CloseOrphan,
    LaunchClaude,
    LaunchOnTask,
    RemoveWorktree,
    ResumeSession,
    StopSession,
    launching_text,
    resuming_text,
    stopping_text,
)
from meute.core.errors import MeuteError, PromptNotPasted
from meute.core.orphans import Orphan, closing_text, orphan_agent
from meute.core.session import Session, SessionId
from meute.core.task import TaskId

# Told on the app's thread when an action ended: its error, or a notice, or neither.
Finished = Callable[[str | None, str | None], None]


class BoardWorkers:
    """Runs the stops, resumes and launches on tasks off the app's thread, one at a time each."""

    def __init__(
        self, app: App[None], perform: Callable[[BoardAction], None], finished: Finished
    ) -> None:
        self._app = app
        self._perform = perform
        self._finished = finished
        self._stopping: dict[SessionId, str] = {}  # sessions being stopped: id -> title
        self._launching: dict[TaskId, None] = {}  # tasks being launched on, in order
        self._resuming: dict[SessionId, str] = {}  # sessions being resumed: id -> title
        # Orphans being adopted or closed, by their tmux identifier: the selection may move.
        self._adopting: dict[str, None] = {}
        self._closing: dict[str, str] = {}  # id -> command
        self._removing: dict[Path, None] = {}  # worktrees being removed

    def is_stopping(self, session_id: SessionId) -> bool:
        """Whether the session is being stopped."""
        return session_id in self._stopping

    def stop(self, session: Session) -> None:
        """Stop `session` in a thread worker: tmux may take seconds to answer."""
        self._stopping[session.id] = session.title
        self._run(StopSession(session_id=session.id), partial(self._stopping.pop, session.id))

    def launch(self, task_id: TaskId) -> None:
        """Launch Claude on a task in a thread worker; ignored while that launch runs."""
        if task_id in self._launching:
            return
        self._launching[task_id] = None
        self._run(LaunchOnTask(task_id=task_id), partial(self._launching.pop, task_id))

    def launch_form(self, action: LaunchClaude, ended: Callable[[str | None], None]) -> bool:
        """Launch the form's Claude on its task in a thread worker, its text pasted like `L`.

        `ended` gets the error, or `None`, on the app's thread; a notice goes to the footer.
        `False`, and nothing runs, without a task or while a launch on that task runs.
        """
        task_id = action.task_id
        if task_id is None or task_id in self._launching:
            return False
        self._launching[task_id] = None
        self._run(action, partial(self._launching.pop, task_id), partial(self._form_ended, ended))
        return True

    def _form_ended(
        self, ended: Callable[[str | None], None], error: str | None, notice: str | None
    ) -> None:
        ended(error)
        self._finished(None, notice)

    def is_resuming(self, session_id: SessionId) -> bool:
        """Whether the session is being resumed."""
        return session_id in self._resuming

    def resume(self, session: Session) -> None:
        """Resume `session` in a thread worker; ignored while it is resumed or stopped."""
        if session.id in self._resuming or session.id in self._stopping:
            return
        self._resuming[session.id] = session.title
        self._run(ResumeSession(session_id=session.id), partial(self._resuming.pop, session.id))

    def is_closing(self, orphan: Orphan) -> bool:
        """Whether the orphan pane is being closed."""
        return orphan.meute_id in self._closing

    def adopt(self, orphan: Orphan) -> None:
        """Adopt `orphan` in a thread worker; ignored while it is being adopted or closed."""
        key = orphan.meute_id
        if self._orphan_busy(key):
            return
        self._adopting[key] = None
        self._run(AdoptOrphan(orphan=orphan), partial(self._adopting.pop, key))

    def close(self, orphan: Orphan) -> None:
        """Close the orphan pane in a thread worker; ignored while it is adopted or closed."""
        key = orphan.meute_id
        if self._orphan_busy(key):
            return
        self._closing[key] = orphan.command
        self._run(
            CloseOrphan(meute_id=key, agent=orphan_agent(orphan)), partial(self._closing.pop, key)
        )

    def is_removing(self, path: Path) -> bool:
        """Whether the worktree `path` is being removed."""
        return path in self._removing

    def remove_worktree(self, action: RemoveWorktree, path_text: str) -> None:
        """Remove a worktree in a thread worker; the footer then names it as `path_text`."""
        if action.path in self._removing:
            return
        self._removing[action.path] = None
        told = partial(self._removed, path_text)
        self._run(action, partial(self._removing.pop, action.path), told)

    def _removed(self, path_text: str, error: str | None, notice: str | None) -> None:
        self._finished(error, f"worktree removed: {path_text}" if error is None else notice)

    def _orphan_busy(self, key: str) -> bool:
        """Whether the orphan is being adopted or closed: either excludes the other."""
        return key in self._adopting or key in self._closing

    def footer(self) -> str | None:
        """What the latest running action says in the footer, if any action runs."""
        if self._stopping:
            return stopping_text(next(reversed(self._stopping.values())))
        if self._resuming:
            return resuming_text(next(reversed(self._resuming.values())))
        if self._closing:
            return closing_text(next(reversed(self._closing.values())))
        if self._launching:
            return launching_text(next(reversed(self._launching)))
        return None

    def _run(
        self, action: BoardAction, forget: Callable[[], object], told: Finished | None = None
    ) -> None:
        work = partial(self._off_thread, action, forget, told or self._finished)
        _ = self._app.run_worker(work, thread=True)

    def _off_thread(
        self, action: BoardAction, forget: Callable[[], object], told: Finished
    ) -> None:
        """Run in the worker thread: only `call_from_thread` may touch the app from here."""
        error: str | None = None
        notice: str | None = None
        try:
            self._perform(action)
        except PromptNotPasted as untold:
            notice = str(untold)
        except MeuteError as failure:
            error = str(failure)
        except Exception as failure:  # noqa: BLE001 — the action must end on screen whatever broke
            error = str(failure) or type(failure).__name__
        with suppress(RuntimeError):  # the app already quit: nobody left to tell
            self._app.call_from_thread(self._ended, forget, told, error, notice)

    @staticmethod
    def _ended(
        forget: Callable[[], object], told: Finished, error: str | None, notice: str | None
    ) -> None:
        _ = forget()
        told(error, notice)
