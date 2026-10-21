"""The Sessions tab: its cursor, its keys and clicks, the stop confirmation."""

from collections.abc import Callable
from datetime import tzinfo
from typing import assert_never

from textual.content import Content

from meute.core.board_header import board_totals
from meute.core.board_sessions import line_at, line_entry, line_group, line_info
from meute.core.board_view import (
    FOOTER,
    KEYS_HELP,
    BoardAction,
    BoardData,
    BoardEntry,
    LaunchBash,
    LaunchClaude,
    LaunchEntry,
    OrphanEntry,
    ShowPane,
    claude_action,
    confirm_stop_text,
    ended_notice,
    enter_action,
    new_action,
    resume_target,
    stop_target,
)
from meute.core.orphans import ORPHAN_FOOTER, ORPHAN_KEYS, Orphan, adoption, confirm_close_text
from meute.core.session import Session, SessionId
from meute.core.sessions_view import (
    CardLine,
    HeaderLine,
    InfoLine,
    OrphanLine,
    RefLine,
    RepoLine,
    SectionLine,
    SessionLine,
    section_key,
    session_index,
)
from meute.tui.launch_form import FormSession, LaunchTask
from meute.tui.sessions_cursor import SessionsCursor
from meute.tui.sessions_pane import details_content, quota_content, view_content

_ACTION_KEYS = frozenset({"enter", "c", "n", "r", "x"})
_SESSION_ONLY_KEYS = frozenset({"c", "n", "r"})


class SessionsTab:
    """The Sessions view; the board gives it where to send actions, notices and stops."""

    def __init__(  # noqa: PLR0913 — the board's callbacks and options, all keyword-only
        self,
        *,
        perform: Callable[[BoardAction], None],
        notice: Callable[[str], None],
        stop: Callable[[Session], None],
        is_stopping: Callable[[SessionId], bool],
        resume: Callable[[Session], None],
        is_resuming: Callable[[SessionId], bool],
        adopt: Callable[[Orphan], None],
        close: Callable[[Orphan], None],
        is_closing: Callable[[Orphan], bool],
        launch: Callable[[LaunchBash | LaunchClaude], None],
        launch_task: LaunchTask,
        default_mode: str,
        local: tzinfo,
        show_details: bool,
    ) -> None:
        self._perform = perform
        self._notice = notice
        self._stop = stop
        self._is_stopping = is_stopping
        self._resume = resume
        self._is_resuming = is_resuming
        self._adopt = adopt
        self._close = close
        self._is_closing = is_closing
        self._form = FormSession(launch=launch, launch_task=launch_task, default_mode=default_mode)
        self._local = local
        self._show_details = show_details
        self.cursor = SessionsCursor()
        self._confirming: Session | Orphan | None = None

    @property
    def width(self) -> int:
        """The width the cards are laid out for."""
        return self.cursor.width

    @property
    def selected(self) -> int:
        """The selected line of the view, -1 when nothing is selectable."""
        return self.cursor.selected

    def totals(self) -> str:
        """The live sessions with their summed duration and cost."""
        return board_totals(self.cursor.model.data)

    def rebuild(self, data: BoardData, width: int) -> None:
        """Take the new data, keeping the selection and the folds."""
        _ = width  # the cards follow the board's own width, given to `fit`
        self.cursor.rebuild(data)
        self._form.refresh(data)

    def fit(self, width: int) -> bool:
        """Lay the cards out for `width`; `True` when that changed them."""
        if width == self.cursor.width:
            return False
        self.cursor.resize(width)
        return True

    def handle_key(self, key: str) -> bool:
        """Apply `key`; `False` when the board should deal with it."""
        confirming, self._confirming = self._confirming, None
        if confirming is not None:  # a pending stop swallows any key
            if key == "y":
                match confirming:
                    case Session():
                        self._stop(confirming)
                    case Orphan():
                        self._close(confirming)
                    case _:
                        assert_never(confirming)
            return True
        if key == "a" and isinstance(self._selected_entry(), OrphanEntry):
            self._act(key)  # on an orphan pane `a` adopts; elsewhere it filters the view
            return True
        if self.cursor.handle_key(key):
            return True
        if key == "N":
            self._form.open(self.cursor.model.data, self._selected_entry())
            return True
        if key in _ACTION_KEYS:
            self._act(key)
            return True
        return False

    @property
    def form_open(self) -> bool:
        """Whether the launch form is open: it takes every key."""
        return self._form.is_open

    def form_key(self, key: str, character: str | None) -> None:
        """Apply `key` to the open launch form."""
        self._form.key(key, character, self.cursor.model.data)

    def form_paste(self, text: str) -> None:
        """Add pasted `text` to the open launch form."""
        self._form.paste(text)

    def form(self, width: int) -> Content | None:
        """The launch form in colour, or `None` when it is closed."""
        return self._form.content(self.cursor.model.data, width)

    def _selected_entry(self) -> BoardEntry | None:
        return line_entry(self.cursor.model, self.cursor.selected)

    def _act(self, key: str) -> None:
        entry = self._selected_entry()
        if entry is None:
            group = line_group(self.cursor.model, self.cursor.selected)  # a folded group's header
            if key == "enter" and group is not None:
                self.cursor.fold(group, fold=False)
        elif isinstance(entry, OrphanEntry):
            self._act_on_orphan(key, entry.orphan)
        elif key == "enter":
            self._show(entry)
        elif key == "c":
            self._perform(claude_action(entry))
        elif key == "n":
            self._perform(new_action(entry, self.cursor.model.data))
        elif key == "r":
            self._resume_entry(entry)
        elif key == "x":
            target = stop_target(entry)
            self._confirming = None if target is None or self._is_stopping(target.id) else target

    def _act_on_orphan(self, key: str, orphan: Orphan) -> None:
        """Enter shows the pane, `a` adopts it, `x` asks before closing it."""
        if key in _SESSION_ONLY_KEYS:
            self._notice(ORPHAN_KEYS)
        elif key == "enter":
            self._perform(ShowPane(pane_id=orphan.pane_id))
        elif key == "a":
            refusal = adoption(orphan, self.cursor.model.data.repos)
            if isinstance(refusal, str):
                self._notice(refusal)
            else:
                self._adopt(orphan)
        elif key == "x" and not self._is_closing(orphan):
            self._confirming = orphan

    def _resume_entry(self, entry: LaunchEntry) -> None:
        """Resume the entry's session, or say why not; left alone while it is resumed or stopped."""
        target = resume_target(entry, self.cursor.model.data.details)
        if isinstance(target, str):
            self._notice(target)
        elif not self._is_resuming(target.id) and not self._is_stopping(target.id):
            self._resume(target)

    def click(self, y: int, x: int) -> None:
        """Select or fold the line at row `y`; like a key, a click only cancels a stop."""
        _ = x
        if self._confirming is not None:
            self._confirming = None
            return
        line = line_at(self.cursor.model, y)
        match line:
            case SessionLine():
                self.cursor.selected = y
                entry = line_entry(self.cursor.model, y)
                if entry is not None and not isinstance(entry, OrphanEntry):
                    self._show(entry)
            case RepoLine() | OrphanLine():
                self.cursor.selected = y
            case CardLine() | RefLine():  # the card's first line, in "Needs you" for a reference
                index = session_index(self.cursor.model.view, line.session_id)
                self.cursor.selected = index if index >= 0 else self.cursor.selected
            case HeaderLine():
                self.cursor.fold(line.group, fold=not line.collapsed)
            case SectionLine():
                self.cursor.fold(section_key(line.section), fold=not line.collapsed)
            case InfoLine() | None:
                pass
            case _:
                assert_never(line)

    def _show(self, entry: LaunchEntry) -> None:
        """Do what Enter does on `entry`, or say why an ended session cannot show."""
        notice = ended_notice(entry)
        if notice is None:
            self._perform(enter_action(entry))
        else:
            self._notice(notice)

    def lines(self, *, focused: bool) -> Content:
        """The grouped sessions, the selected card highlighted."""
        return view_content(
            self.cursor.model, self.cursor.selected, focused=focused, width=self.cursor.width
        )

    def quota(self, width: int) -> Content | None:
        """The quota bars and a rule under them, when the usage is known."""
        quota = self.cursor.model.data.quota
        return None if quota is None else quota_content(quota, self._local, width)

    def details(self, width: int) -> Content | None:
        """The selected session's details, when shown and there is one."""
        if not self._show_details:
            return None
        info = line_info(self.cursor.model, self.cursor.selected)
        return None if info is None else details_content(self.cursor.model, info, width)

    def prompt(self) -> str | None:
        """The pending stop confirmation, which takes over the footer."""
        match self._confirming:
            case None:
                return None
            case Session():
                return confirm_stop_text(self._confirming.title)
            case Orphan():
                return confirm_close_text(self._confirming.command)
            case _:
                assert_never(self._confirming)

    def footer(self) -> str:
        """The one-line keys; an orphan pane has its own."""
        return ORPHAN_FOOTER if isinstance(self._selected_entry(), OrphanEntry) else FOOTER

    def keys_help(self) -> str:
        """The full list of keys."""
        return KEYS_HELP
