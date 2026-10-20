"""Tests of the quick postpones of a task."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from meute.core.instants import parse_zoned
from meute.core.task import DueAt
from meute.core.task_postpone import Postpone, postpone
from support import NOW, at_due


def test_labels() -> None:
    assert [p.value for p in Postpone] == [
        "+1h",
        "tonight 6pm",
        "tomorrow 9am",
        "Monday 9am",
        "clear",
    ]


@pytest.mark.parametrize(
    ("now", "choice", "expected"),
    [
        ("2026-10-14T10:30[Europe/Paris]", Postpone.HOUR, "2026-10-14T11:30[Europe/Paris]"),
        ("2026-10-14T10:30[Europe/Paris]", Postpone.TONIGHT, "2026-10-14T18:00[Europe/Paris]"),
        ("2026-10-14T18:30[Europe/Paris]", Postpone.TONIGHT, "2026-10-15T18:00[Europe/Paris]"),
        ("2026-10-14T18:00[Europe/Paris]", Postpone.TONIGHT, "2026-10-15T18:00[Europe/Paris]"),
        ("2026-10-14T23:59[Europe/Paris]", Postpone.TONIGHT, "2026-10-15T18:00[Europe/Paris]"),
        ("2026-10-14T23:59[Europe/Paris]", Postpone.TOMORROW, "2026-10-15T09:00[Europe/Paris]"),
        ("2026-10-14T10:30[Europe/Paris]", Postpone.TOMORROW, "2026-10-15T09:00[Europe/Paris]"),
        ("2026-10-14T10:30[Europe/Paris]", Postpone.MONDAY, "2026-10-19T09:00[Europe/Paris]"),
        ("2026-10-19T08:00[Europe/Paris]", Postpone.MONDAY, "2026-10-19T09:00[Europe/Paris]"),
        ("2026-10-19T09:00[Europe/Paris]", Postpone.MONDAY, "2026-10-26T09:00[Europe/Paris]"),
        ("2026-10-18T23:59[Europe/Paris]", Postpone.MONDAY, "2026-10-19T09:00[Europe/Paris]"),
        # The night before the switch to summer time: the day is 23 hours long.
        ("2026-03-28T20:00[Europe/Paris]", Postpone.TOMORROW, "2026-03-29T09:00[Europe/Paris]"),
        ("2026-03-28T20:00[Europe/Paris]", Postpone.HOUR, "2026-03-28T21:00[Europe/Paris]"),
        ("2026-03-29T01:30[Europe/Paris]", Postpone.HOUR, "2026-03-29T03:30[Europe/Paris]"),
        ("2026-03-29T09:30[Europe/Paris]", Postpone.TONIGHT, "2026-03-29T18:00[Europe/Paris]"),
        ("2026-03-27T10:00[Europe/Paris]", Postpone.MONDAY, "2026-03-30T09:00[Europe/Paris]"),
    ],
)
def test_postpone(now: str, choice: Postpone, expected: str) -> None:
    assert postpone(choice, parse_zoned(now)) == at_due(expected)


def test_hour_is_real_time_across_the_switch() -> None:
    now = parse_zoned("2026-03-29T01:30[Europe/Paris]")
    due = postpone(Postpone.HOUR, now)
    assert isinstance(due, DueAt)
    assert due.at - now == timedelta(hours=1)


def test_clear() -> None:
    assert postpone(Postpone.CLEAR, NOW) is None


_PARIS = ZoneInfo("Europe/Paris")
_DST_DAYS = [
    *(date(2026, 3, 28), date(2026, 3, 29), date(2026, 10, 24), date(2026, 10, 25)),
    *(date(2027, 3, 28), date(2027, 10, 31)),
]
_TARGETS = {Postpone.TONIGHT: time(18), Postpone.TOMORROW: time(9), Postpone.MONDAY: time(9)}


def _paris(day: date, at: time) -> datetime:
    """A real instant of Paris: a wall-clock time in the spring gap is moved forward."""
    return datetime.combine(day, at, tzinfo=_PARIS).astimezone(UTC).astimezone(_PARIS)


_DAYS = st.one_of(st.dates(date(2026, 1, 1), date(2030, 12, 31)), st.sampled_from(_DST_DAYS))


_TIMES = st.one_of(st.times(), st.sampled_from([time(9), time(18)]))  # the edges, often


@given(day=_DAYS, at=_TIMES, choice=st.sampled_from(Postpone))
def test_postpone_lands_after_now_at_its_wall_time(day: date, at: time, choice: Postpone) -> None:
    now = _paris(day, at)
    due = postpone(choice, now)
    if choice is Postpone.CLEAR:
        assert due is None
        return
    assert isinstance(due, DueAt)
    if choice is Postpone.HOUR:
        assert due.at - now == timedelta(hours=1)
        return
    assert due.at > now
    local = due.at.astimezone(_PARIS)
    wanted = _TARGETS[choice]
    assert local.time() == _paris(local.date(), wanted).time()
    assert local.time() in {wanted, time(wanted.hour + 1)}
    if choice is Postpone.MONDAY:
        assert local.weekday() == 0
