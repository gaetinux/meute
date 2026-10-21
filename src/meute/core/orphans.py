"""Orphan panes: panes marked for meute whose `@meute_id` matches no session."""

from dataclasses import dataclass
from pathlib import Path

from meute.core.paths import display_path
from meute.core.text import printable

ORPHAN_KEYS = "orphan pane: Enter show · a adopt · x close"
"""What an orphan pane answers to the keys that act on sessions."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Orphan:
    """A pane carrying a `@meute_id` unknown to the database, as tmux describes it.

    Every field comes from tmux and may hold anything: show it through `printable`, and
    check `meute_id` before writing it anywhere.
    """

    meute_id: str
    pane_id: str
    command: str
    cwd: str
    dead: bool


def orphan_line(orphan: Orphan, home: Path | None) -> str:
    """Return `? {command}  {folder}  orphan` (`dead` for a dead pane) on one printable line."""
    folder = display_path(Path(orphan.cwd), home) if orphan.cwd else ""
    state = "dead" if orphan.dead else "orphan"
    return f"? {printable(orphan.command)}  {printable(folder)}  {state}"
