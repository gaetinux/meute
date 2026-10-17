from datetime import UTC, datetime

import pytest

from meute.core.due_parse import parse_due
from meute.core.instants import parse_zoned
from meute.core.task import Due, DueAt
from support import NOW, at_due, date_due

P = "[Europe/Paris]"


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("tomorrow", date_due("2026-10-15")),
        ("tonight", at_due(f"2026-10-14T18:00{P}")),
        ("mon", date_due("2026-10-19")),
        ("wed", date_due("2026-10-21")),
        ("mon-9am", at_due(f"2026-10-19T09:00{P}")),
        ("mon-2pm", at_due(f"2026-10-19T14:00{P}")),
        ("fri-2pm", at_due(f"2026-10-16T14:00{P}")),
        ("+2h", at_due(f"2026-10-14T12:30{P}")),
        ("+30m", at_due(f"2026-10-14T11:00{P}")),
        ("+3d", at_due(f"2026-10-17T10:30{P}")),
        ("2026-10-20", date_due("2026-10-20")),
        ("2026-10-20T14:00", at_due(f"2026-10-20T14:00{P}")),
        ("Tomorrow", date_due("2026-10-15")),
        ("MON-9AM", at_due(f"2026-10-19T09:00{P}")),
    ],
)
def test_due_forms_from_spec(token: str, expected: Due) -> None:
    assert parse_due(token, NOW) == expected


@pytest.mark.parametrize(
    ("name", "day"),
    [
        ("mon", "2026-10-19"),
        ("tue", "2026-10-20"),
        ("wed", "2026-10-21"),
        ("thu", "2026-10-15"),
        ("fri", "2026-10-16"),
        ("sat", "2026-10-17"),
        ("sun", "2026-10-18"),
    ],
)
def test_every_weekday_name_is_strictly_after_today(name: str, day: str) -> None:
    assert parse_due(name, NOW) == date_due(day)


def test_twelve_hour_bounds() -> None:
    assert parse_due("mon-12am", NOW) == at_due(f"2026-10-19T00:00{P}")
    assert parse_due("mon-12pm", NOW) == at_due(f"2026-10-19T12:00{P}")
    assert parse_due("mon-11pm", NOW) == at_due(f"2026-10-19T23:00{P}")


@pytest.mark.parametrize(
    "token",
    [
        "mon-0am",
        "mon-13pm",
        "mon-9",
        "mon-14:00",
        "mon-2:30pm",
        "mon-9:00am",
        "mon-009am",
        "2026-10-14 16:45",
        "2026-02-30",
        "2026-10-20T25:00",
        "+0h",
        "+10000h",
        "+2w",
        "+h",
        "soon",
        "20261020",
        "2026-W42-3",
        "2026-10-20T14",
        "2026-10-20T14:00Z",
        "2026-10-20T14:00:00",
        "0001-01-01T00:00",
        "+٣h",
        "+²h",
        "mon-٩am",
        "mon-+5pm",
        "",
        "monday",
    ],
)
def test_rejected_tokens(token: str) -> None:
    assert parse_due(token, NOW) is None


def test_delta_upper_bound_is_inclusive() -> None:
    assert parse_due("+9999h", NOW) is not None


# Daylight saving time: the eve of the switch to summer time.
SPRING = parse_zoned(f"2026-03-28T10:30{P}")


def test_dst_hours_are_real_time_and_days_are_wall_time() -> None:
    assert parse_due("+24h", SPRING) == at_due(f"2026-03-29T11:30{P}")
    assert parse_due("+1d", SPRING) == at_due(f"2026-03-29T10:30{P}")


def test_dst_gap_is_shifted_forward_and_ambiguous_time_takes_first() -> None:
    assert parse_due("2026-03-29T02:30", SPRING) == at_due(f"2026-03-29T03:30{P}")
    assert parse_due("2026-10-25T02:30", NOW) == DueAt(at=datetime(2026, 10, 25, 0, 30, tzinfo=UTC))
