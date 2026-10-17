"""Tests added after mutmut: model JSON forms, messages and time-zone handling."""

import os
import time
from collections.abc import Generator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from meute.core.actor import Author, Channel
from meute.core.due_parse import parse_due
from meute.core.errors import ConfigError, InvalidInput
from meute.core.instants import parse_zoned, to_db, utc_now
from meute.core.paths import Paths
from meute.core.project import Project, ProjectId, ProjectRef, RepoId, project_to_json
from meute.core.status import Blocked, Done, StatusKind, status_from_kind
from meute.core.task import (
    DueAt,
    Note,
    TaskId,
    due_from_json,
    note_to_json,
    task_to_json,
)
from meute.core.views import Bucket, bucket_of, format_due, sort_for_display
from support import FIXED, NOW, at_due, date_due, make_task


@pytest.fixture
def system_in_auckland() -> Generator[None]:
    """Make the process time zone differ from Paris, so a stray local-time call shows."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Pacific/Auckland"
    time.tzset()
    yield
    if previous is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = previous
    time.tzset()


def test_utc_now_is_aware_and_in_utc() -> None:
    now = utc_now()
    assert now.tzinfo is UTC
    assert abs((datetime.now(UTC) - now).total_seconds()) < 5


def test_naive_datetime_is_refused_with_a_message() -> None:
    with pytest.raises(ValueError, match=r"^cannot store a naive datetime$"):
        to_db(datetime(2026, 10, 14, 8, 30))  # noqa: DTZ001 — the naive input is the point


@pytest.mark.parametrize(
    "text", ["tomorrow", "2026-10-14T10:30[Not/AZone]", "2026-13-45T10:30[Europe/Paris]"]
)
def test_invalid_zoned_time_names_the_text(text: str) -> None:
    with pytest.raises(InvalidInput) as raised:
        parse_zoned(text)
    assert str(raised.value) == f"invalid zoned time: {text}"


def test_blocked_without_reason_message() -> None:
    with pytest.raises(InvalidInput, match=r"^a blocked task needs a non-empty reason$"):
        Blocked(reason="")


def test_config_error_exposes_its_path_and_reason() -> None:
    error = ConfigError(Path("/x/config.toml"), "bad")
    assert (error.path, error.message) == (Path("/x/config.toml"), "bad")
    assert str(error) == "invalid configuration (/x/config.toml): bad"


def test_ensure_dirs_can_run_twice(tmp_path: Path) -> None:
    paths = Paths.from_roots(
        config_home=tmp_path / "c", data_home=tmp_path / "d", state_home=tmp_path / "s"
    )
    paths.ensure_dirs()
    paths.ensure_dirs()
    assert paths.db_file.parent.is_dir()
    assert paths.config_file.parent.is_dir()
    assert paths.state_dir.is_dir()


def test_a_one_o_clock_time_is_accepted() -> None:
    assert parse_due("mon-1am", NOW) == at_due("2026-10-19T01:00[Europe/Paris]")
    assert parse_due("mon-1pm", NOW) == at_due("2026-10-19T13:00[Europe/Paris]")


@pytest.mark.usefixtures("system_in_auckland")
def test_due_at_is_normalised_to_utc_whatever_the_system_zone() -> None:
    due = DueAt(at=parse_zoned("2026-10-14T10:30[Europe/Paris]"))
    assert due.at.tzinfo is UTC
    with pytest.raises(ValueError, match=r"^a due instant cannot be a naive datetime$"):
        DueAt(at=datetime(2026, 10, 14, 10, 30))  # noqa: DTZ001 — the naive input is the point


def test_due_from_json_rejects_unknown_shapes_with_a_message() -> None:
    with pytest.raises(InvalidInput, match=r"^invalid due: \{'kind': 'other', 'value': 'x'\}$"):
        due_from_json({"kind": "other", "value": "x"})
    with pytest.raises(InvalidInput, match=r"^invalid due: Invalid isoformat string: 'x'$"):
        due_from_json({"kind": "at", "value": "x"})
    with pytest.raises(InvalidInput, match=r"^invalid due: Invalid isoformat string: 'x'$"):
        due_from_json({"kind": "date", "value": "x"})


def test_task_json_of_a_plain_task() -> None:
    assert task_to_json(make_task(3)) == {
        "id": 3,
        "title": "task 3",
        "description": "",
        "status": "todo",
        "blocked_reason": None,
        "priority": "normal",
        "due": None,
        "project": None,
        "repo_id": None,
        "version": 1,
        "created_at": "2026-10-14T08:30:00Z",
        "updated_at": "2026-10-14T08:30:00Z",
        "completed_at": None,
    }


def test_task_json_of_a_full_task() -> None:
    task = replace(
        make_task(4, due=date_due("2026-10-20"), status=Done(), completed_at=FIXED),
        project=ProjectRef(id=ProjectId(2), name="meute"),
        repo_id=RepoId(5),
    )
    data = task_to_json(task)
    assert data["project"] == {"id": 2, "name": "meute"}
    assert data["due"] == {"kind": "date", "value": "2026-10-20"}
    assert data["completed_at"] == "2026-10-14T08:30:00Z"
    assert data["repo_id"] == 5
    blocked = task_to_json(make_task(5, status=Blocked(reason="CI")))
    assert (blocked["status"], blocked["blocked_reason"]) == ("blocked", "CI")


def test_note_json() -> None:
    note = Note(
        id=9,
        task_id=TaskId(3),
        body="hello",
        author=Author.CLAUDE,
        channel=Channel.MCP,
        session_id="s-1",
        created_at=FIXED,
    )
    assert note_to_json(note) == {
        "id": 9,
        "task_id": 3,
        "body": "hello",
        "author": "claude",
        "channel": "mcp",
        "session_id": "s-1",
        "created_at": "2026-10-14T08:30:00Z",
    }


def test_project_json() -> None:
    project = Project(
        id=ProjectId(2),
        name="meute",
        description="d",
        instructions="i",
        created_at=FIXED,
    )
    assert project_to_json(project) == {
        "id": 2,
        "name": "meute",
        "description": "d",
        "instructions": "i",
        "created_at": "2026-10-14T08:30:00Z",
    }


def test_a_later_time_on_a_future_day_is_upcoming_not_today() -> None:
    tomorrow = make_task(1, due=at_due("2026-10-15T09:00[Europe/Paris]"))
    assert bucket_of(tomorrow, NOW) is Bucket.UPCOMING
    later_today = make_task(2, due=at_due("2026-10-14T18:00[Europe/Paris]"))
    assert bucket_of(later_today, NOW) is Bucket.TODAY


@pytest.mark.usefixtures("system_in_auckland")
def test_days_are_read_in_the_zone_of_now_not_the_system_zone() -> None:
    # 23:30 in Paris is already the next day in Auckland.
    late = make_task(1, due=at_due("2026-10-14T23:30[Europe/Paris]"))
    assert bucket_of(late, NOW) is Bucket.TODAY
    assert late.due is not None
    assert format_due(late.due, NOW) == "today 11:30pm"
    done = make_task(2, status=Done(), completed_at=parse_zoned("2026-10-14T23:30[Europe/Paris]"))
    assert bucket_of(done, NOW) is Bucket.DONE_TODAY


def test_a_date_due_sorts_at_the_last_second_of_the_day() -> None:
    dated = make_task(1, due=date_due("2026-10-20"))
    half_a_minute_early = datetime(2026, 10, 20, 23, 59, 30, tzinfo=ZoneInfo("Europe/Paris"))
    timed = make_task(2, due=DueAt(at=half_a_minute_early))
    assert [t.id for t in sort_for_display([dated, timed], NOW)] == [timed.id, dated.id]


def test_done_status_is_built_from_its_kind() -> None:
    assert status_from_kind(StatusKind.DONE) == Done()
