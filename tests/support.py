"""Helpers shared by the tests: plain functions, not fixtures."""

from datetime import date

from meute.core.instants import parse_zoned
from meute.core.task import DueAt, DueDate

NOW = parse_zoned("2026-10-14T10:30[Europe/Paris]")  # a Wednesday


def date_due(text: str) -> DueDate:
    """Build a date-only due from `YYYY-MM-DD`."""
    return DueDate(day=date.fromisoformat(text))


def at_due(zoned: str) -> DueAt:
    """Build a due with a time from `YYYY-MM-DDTHH:MM[Zone]`."""
    return DueAt(at=parse_zoned(zoned))
