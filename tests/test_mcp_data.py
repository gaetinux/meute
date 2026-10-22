"""Tests of the MCP tool inputs and the task JSON."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st
from syrupy.assertion import SnapshotAssertion

from meute.core.actor import Author, Channel
from meute.core.errors import InvalidInput
from meute.core.instants import parse_zoned
from meute.core.mcp_data import (
    DueFilter,
    due_matches,
    parse_due,
    parse_due_filter,
    parse_priority,
    parse_status,
    task_json,
    task_summary_json,
)
from meute.core.project import ProjectId, ProjectRef
from meute.core.status import Blocked, Done, InProgress, Priority, Review, Todo
from meute.core.task import Due, DueAt, DueDate, Note, TaskId, due_text
from support import NOW, at_due, date_due, make_task

P = "[Europe/Paris]"
DUE_ERROR = "due must be a date (YYYY-MM-DD) or an instant with a time zone: "


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("todo", Todo()),
        ("in_progress", InProgress()),
        ("review", Review()),
        ("done", Done()),
    ],
)
def test_a_status_without_reason(text: str, expected: object) -> None:
    assert parse_status(text, None) == expected


def test_blocked_keeps_its_trimmed_reason() -> None:
    assert parse_status("blocked", "  waiting for CI ") == Blocked(reason="waiting for CI")


def test_unknown_status() -> None:
    with pytest.raises(InvalidInput, match=r"^unknown status: started$"):
        parse_status("started", None)


@pytest.mark.parametrize("reason", [None, "", "   \n"])
def test_blocked_needs_a_reason(reason: str | None) -> None:
    with pytest.raises(InvalidInput, match=r"^blocked needs a reason$"):
        parse_status("blocked", reason)


@pytest.mark.parametrize("text", ["todo", "in_progress", "review", "done"])
@pytest.mark.parametrize("reason", ["because", ""])
def test_a_reason_only_goes_with_blocked(text: str, reason: str) -> None:
    with pytest.raises(InvalidInput, match=r"^a reason only goes with blocked$"):
        parse_status(text, reason)


def test_priority() -> None:
    assert parse_priority("urgent") is Priority.URGENT
    with pytest.raises(InvalidInput, match=r"^unknown priority: Urgent$"):
        parse_priority("Urgent")


def test_due_forms() -> None:
    assert parse_due("2026-10-20") == date_due("2026-10-20")
    assert parse_due("2026-10-20T14:00:00+02:00") == at_due(f"2026-10-20T14:00{P}")
    assert parse_due("2026-10-20T12:00:00Z") == at_due(f"2026-10-20T14:00{P}")
    assert parse_due("2026-10-20T12:00:00.250000Z") == DueAt(
        at=datetime(2026, 10, 20, 12, 0, 0, 250000, tzinfo=UTC)
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "tomorrow",
        "2026-10-20T14:00",
        "2026-10-20T14:00:00",
        "2026-13-01",
        "20261020",
        "2026-10-20 ",
    ],
)
def test_invalid_dues(text: str) -> None:
    with pytest.raises(InvalidInput) as raised:
        parse_due(text)
    assert str(raised.value) == DUE_ERROR + text


@given(
    st.one_of(
        st.dates().map(lambda day: DueDate(day=day)),
        st.datetimes(timezones=st.timezones() | st.just(UTC)).map(lambda at: DueAt(at=at)),
    )
)
def test_due_text_round_trips(due: Due) -> None:
    assert parse_due(due_text(due)) == due


def test_due_filter() -> None:
    assert parse_due_filter("week") is DueFilter.WEEK
    with pytest.raises(InvalidInput, match=r"^unknown due filter: month$"):
        parse_due_filter("month")


def _matches(due: Due | None, now: datetime = NOW) -> tuple[bool, bool, bool]:
    return (
        due_matches(due, DueFilter.OVERDUE, now),
        due_matches(due, DueFilter.TODAY, now),
        due_matches(due, DueFilter.WEEK, now),
    )


def test_no_due_matches_nothing() -> None:
    assert _matches(None) == (False, False, False)


def test_dates_around_today() -> None:
    assert _matches(date_due("2026-10-13")) == (True, False, False)
    assert _matches(date_due("2026-10-14")) == (False, True, True)
    assert _matches(date_due("2026-10-20")) == (False, False, True)
    assert _matches(date_due("2026-10-21")) == (False, False, False)


def test_instants_around_now() -> None:
    assert _matches(DueAt(at=NOW - timedelta(seconds=1))) == (True, True, False)
    assert _matches(DueAt(at=NOW)) == (False, True, True)
    assert _matches(DueAt(at=NOW + timedelta(hours=14))) == (False, False, True)


def test_local_midnight_bounds_today() -> None:
    before = at_due(f"2026-10-13T23:59{P}")
    start = at_due(f"2026-10-14T00:00{P}")
    end = at_due(f"2026-10-14T23:59{P}")
    after = at_due(f"2026-10-15T00:00{P}")
    assert [due_matches(d, DueFilter.TODAY, NOW) for d in (before, start, end, after)] == [
        False,
        True,
        True,
        False,
    ]


def test_today_is_read_in_the_zone_of_now() -> None:
    utc_now = datetime(2026, 10, 14, 23, 30, tzinfo=UTC)
    paris_now = utc_now.astimezone(NOW.tzinfo)  # already the 15th in Paris
    due = DueAt(at=datetime(2026, 10, 15, 0, 0, tzinfo=UTC))  # 02:00 on the 15th in Paris
    assert not due_matches(due, DueFilter.TODAY, utc_now)
    assert due_matches(due, DueFilter.TODAY, paris_now)


def _paris(local: str) -> datetime:
    return parse_zoned(f"{local}{P}")


def test_week_edges_for_instants() -> None:
    week = timedelta(days=7)
    assert due_matches(DueAt(at=NOW + week - timedelta(seconds=1)), DueFilter.WEEK, NOW)
    assert not due_matches(DueAt(at=NOW + week), DueFilter.WEEK, NOW)


def test_the_clock_change_day() -> None:
    # Paris falls back on 2026-10-25: that day lasts 25 hours.
    now = _paris("2026-10-25T00:30")
    assert due_matches(date_due("2026-10-25"), DueFilter.TODAY, now)
    assert due_matches(at_due(f"2026-10-25T23:30{P}"), DueFilter.TODAY, now)
    assert not due_matches(at_due(f"2026-10-26T00:00{P}"), DueFilter.TODAY, now)
    assert due_matches(date_due("2026-10-24"), DueFilter.OVERDUE, now)
    assert not due_matches(date_due("2026-10-25"), DueFilter.OVERDUE, now)
    # A week from the 25th at 00:30 local is the 1st at 00:30 local (wall clock).
    assert due_matches(at_due(f"2026-11-01T00:29{P}"), DueFilter.WEEK, now)
    assert not due_matches(at_due(f"2026-11-01T00:30{P}"), DueFilter.WEEK, now)


def test_a_fixed_offset_now() -> None:
    now = datetime(2026, 10, 14, 10, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert due_matches(date_due("2026-10-14"), DueFilter.TODAY, now)


def _note(note_id: int, body: str) -> Note:
    return Note(
        id=note_id,
        task_id=TaskId(7),
        body=body,
        author=Author.CLAUDE,
        channel=Channel.MCP,
        session_id="s-1",
        created_at=datetime(2026, 10, 14, 9, 0, 0, 500000, tzinfo=UTC),
    )


def test_summary_json(snapshot: SnapshotAssertion) -> None:
    task = make_task(
        7,
        due=at_due(f"2026-10-20T14:00{P}"),
        status=Blocked(reason="waiting for CI"),
        priority=Priority.HIGH,
    )
    task = replace(task, project=ProjectRef(id=ProjectId(3), name="meute"))
    bare = make_task(8)
    assert json.dumps([task_summary_json(task), task_summary_json(bare)], indent=2) == snapshot


def test_task_json(snapshot: SnapshotAssertion) -> None:
    done_at = datetime(2026, 10, 14, 9, 30, tzinfo=UTC)
    blocked = replace(
        make_task(7, due=date_due("2026-10-20"), status=Blocked(reason="waiting for CI")),
        description="line one\nline two",
        project=ProjectRef(id=ProjectId(3), name="meute"),
        version=4,
    )
    finished = make_task(8, status=Done(), completed_at=done_at)
    notes = [_note(1, "first"), replace(_note(2, "second"), session_id=None, author=Author.USER)]
    assert (
        json.dumps(
            [task_json(blocked, notes), task_json(finished, [])], indent=2, ensure_ascii=False
        )
        == snapshot
    )


def test_blocked_reason_is_null_outside_blocked() -> None:
    assert task_json(make_task(1, status=InProgress()), [])["blocked_reason"] is None
