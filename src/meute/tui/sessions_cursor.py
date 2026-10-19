"""The Sessions view's navigation: the view state, its lines and the selected one."""

from dataclasses import replace

from meute.core.board_sessions import BoardSessions, board_sessions, line_at, line_group
from meute.core.board_view import BoardData
from meute.core.sessions_view import ViewState, keep_selection, line_key, selectable

_EMPTY = BoardData(sessions=(), repos=(), orphans=(), home=None)


class SessionsCursor:
    """The view state, the lines it gives and the selected line, kept across reloads."""

    def __init__(self) -> None:
        self.state = ViewState()
        self.model: BoardSessions = board_sessions(_EMPTY, self.state)
        self.selected = -1  # a line index of the view; -1: nothing selectable

    def handle_key(self, key: str) -> bool:
        """Apply a navigation or view key; return `False` when `key` is not one."""
        if key in {"up", "k"}:
            self.move(-1)
        elif key in {"down", "j"}:
            self.move(1)
        elif key == "a":
            self.set_state(replace(self.state, attention_only=not self.state.attention_only))
        elif key == "e":
            self.set_state(replace(self.state, show_ended=not self.state.show_ended))
        elif key in {"space", "left", "right"}:
            group = line_group(self.model, self.selected)
            if group is not None:
                folded = group in self.state.collapsed
                self.fold(group, fold=not folded if key == "space" else key == "left")
        else:
            return False
        return True

    def move(self, delta: int) -> None:
        """Move the selection by `delta` selectable lines, stopping at both ends."""
        choices = selectable(self.model.view)
        if choices:
            position = choices.index(self.selected) if self.selected in choices else 0
            self.selected = choices[min(max(position + delta, 0), len(choices) - 1)]

    def fold(self, group: str, *, fold: bool) -> None:
        """Fold or unfold `group`; the selection moves to its header, or into it from there."""
        if fold == (group in self.state.collapsed):
            return
        collapsed = self.state.collapsed
        header_selected = self._selected_key() == f"group:{group}"
        inside = line_group(self.model, self.selected) == group
        self.set_state(
            replace(self.state, collapsed=collapsed | {group} if fold else collapsed - {group}),
            old_group=group if fold and inside else None,
        )
        if not fold and header_selected:
            choices = selectable(self.model.view)
            members = (i for i in choices if line_group(self.model, i) == group)
            self.selected = next(members, self.selected)

    def set_state(self, state: ViewState, *, old_group: str | None = None) -> None:
        """Switch to `state` and rebuild the view from the same data."""
        self.state = state
        self.rebuild(self.model.data, old_group=old_group)

    def rebuild(self, data: BoardData, *, old_group: str | None = None) -> None:
        """Rebuild the view, keeping the selected line when it is still there."""
        choices = selectable(self.model.view)
        position = choices.index(self.selected) if self.selected in choices else 0
        old_key = self._selected_key()
        self.model = board_sessions(data, self.state)
        self.selected = keep_selection(old_key, self.model.view, position, old_group=old_group)

    def _selected_key(self) -> str | None:
        line = line_at(self.model, self.selected)
        return None if line is None else line_key(line)
