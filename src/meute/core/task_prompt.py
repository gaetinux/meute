"""The text pasted into Claude to work on a task."""

from collections.abc import Sequence

from meute.core.task import Note, Task, task_label
from meute.core.text import printable


def _clean(text: str) -> str:
    """Neutralise control characters (no ESC, so no end of bracketed paste) and trim."""
    return printable(text, keep_newlines=True).strip()


def task_prompt(task: Task, notes: Sequence[Note]) -> str:
    """Return `#id title`, the description and the notes (oldest first), as pasted into Claude.

    Every part goes through `printable`, so no escape sequence and no carriage return can survive
    to end the bracketed paste early. The text has no final newline.
    """
    parts = [f"{task_label(task.id)} {_clean(task.title)}"]
    if description := _clean(task.description):
        parts.append(description)
    if notes:
        ordered = sorted(notes, key=lambda note: (note.created_at, note.id))
        parts.append("\n".join(["Notes:", *(f"- {_clean(note.body)}" for note in ordered)]))
    return "\n\n".join(parts)
