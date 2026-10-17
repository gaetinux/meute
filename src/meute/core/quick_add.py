"""Quick entry: `Review the PR @meute ! >tomorrow` into a title and its attributes."""

from dataclasses import dataclass
from datetime import datetime

from meute.core.due_parse import parse_due
from meute.core.errors import InvalidInput
from meute.core.status import Priority
from meute.core.task import Due

_PRIORITIES = {"!": Priority.HIGH, "!!": Priority.URGENT}


@dataclass(frozen=True, slots=True, kw_only=True)
class QuickAdd:
    """The result of parsing a quick entry."""

    title: str
    project: str | None
    priority: Priority
    due: Due | None


def parse_quick_add(text: str, now: datetime) -> QuickAdd:
    """Split `text` into a title, a project (`@name`), a priority (`!`, `!!`) and a due (`>x`).

    Only whitespace-separated tokens starting with `@`, `!` or `>` are candidates;
    unrecognised ones stay in the title. The last project and priority win.

    Raises:
        InvalidInput: the title is empty once the attributes are extracted.
    """
    words: list[str] = []
    project: str | None = None
    priority = Priority.NORMAL
    due: Due | None = None
    for token in text.split():
        if token[0] == "@" and len(token) > 1:
            project = token[1:]
        elif token in _PRIORITIES:
            priority = _PRIORITIES[token]
        elif token[0] == ">" and (parsed := parse_due(token[1:], now)) is not None:
            due = parsed
        else:
            words.append(token)
    if not words:
        message = "empty title"
        raise InvalidInput(message)
    return QuickAdd(title=" ".join(words), project=project, priority=priority, due=due)
