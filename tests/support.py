"""Helpers shared by the tests: plain functions, not fixtures."""

from datetime import UTC, date, datetime

from meute.core.actor import Actor, Author, Channel
from meute.core.instants import parse_zoned
from meute.core.project import ProjectId
from meute.core.task import DueAt, DueDate, NewTask

NOW = parse_zoned("2026-10-14T10:30[Europe/Paris]")  # a Wednesday


def date_due(text: str) -> DueDate:
    """Build a date-only due from `YYYY-MM-DD`."""
    return DueDate(day=date.fromisoformat(text))


def at_due(zoned: str) -> DueAt:
    """Build a due with a time from `YYYY-MM-DDTHH:MM[Zone]`."""
    return DueAt(at=parse_zoned(zoned))


USER = Actor(author=Author.USER, channel=Channel.CLI)
CLAUDE = Actor(author=Author.CLAUDE, channel=Channel.MCP, session_id="s-1")
FIXED = datetime(2026, 10, 14, 8, 30, tzinfo=UTC)


def new_task(title: str, project_id: ProjectId | None = None) -> NewTask:
    """Build a task creation request with default fields."""
    return NewTask(title=title, project_id=project_id)
