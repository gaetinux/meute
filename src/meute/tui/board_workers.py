"""The board's slow actions, each in a thread worker: stopping a session, launching on a task."""

from collections.abc import Callable
from contextlib import suppress
from functools import partial

from textual.app import App

from meute.core.board_view import (
    BoardAction,
    LaunchOnTask,
    StopSession,
    launching_text,
    stopping_text,
)
from meute.core.errors import MeuteError, PromptNotPasted
from meute.core.session import Session, SessionId
from meute.core.task import TaskId

# Told on the app's thread when an action ended: its error, or a notice, or neither.
Finished = Callable[[str | None, str | None], None]


class BoardWorkers:
    """Runs the stops and the launches on tasks off the app's thread, one at a time each."""

    def __init__(
        self, app: App[None], perform: Callable[[BoardAction], None], finished: Finished
    ) -> None:
        self._app = app
        self._perform = perform
        self._finished = finished
        self._stopping: dict[SessionId, str] = {}  # sessions being stopped: id -> title
        self._launching: dict[TaskId, None] = {}  # tasks being launched on, in order

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

    def footer(self) -> str | None:
        """What the latest running action says in the footer, if any action runs."""
        if self._stopping:
            return stopping_text(next(reversed(self._stopping.values())))
        if self._launching:
            return launching_text(next(reversed(self._launching)))
        return None

    def _run(self, action: BoardAction, forget: Callable[[], object]) -> None:
        _ = self._app.run_worker(partial(self._off_thread, action, forget), thread=True)

    def _off_thread(self, action: BoardAction, forget: Callable[[], object]) -> None:
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
            self._app.call_from_thread(self._ended, forget, error, notice)

    def _ended(self, forget: Callable[[], object], error: str | None, notice: str | None) -> None:
        _ = forget()
        self._finished(error, notice)
