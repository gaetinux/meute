"""Tests for the task model and its JSON forms."""

from datetime import UTC, datetime

import pytest

from meute.core.errors import InvalidInput
from meute.core.project import ProjectId, ProjectRef
from meute.core.status import Blocked, Priority
from meute.core.task import (
    DueAt,
    Task,
    TaskId,
    due_from_json,
    due_to_json,
    task_label,
    task_to_json,
)
from support import at_due, date_due


def test_task_json_is_flat_with_tagged_due() -> None:
    ts = datetime(2026, 10, 15, 8, 0, tzinfo=UTC)
    task = Task(
        id=TaskId(3),
        title="t",
        description="",
        status=Blocked(reason="waiting for review"),
        priority=Priority.HIGH,
        due=date_due("2026-10-20"),
        project=ProjectRef(id=ProjectId(1), name="meute"),
        repo_id=None,
        version=2,
        created_at=ts,
        updated_at=ts,
        completed_at=None,
    )
    assert task_to_json(task) == {
        "id": 3,
        "title": "t",
        "description": "",
        "status": "blocked",
        "blocked_reason": "waiting for review",
        "priority": "high",
        "due": {"kind": "date", "value": "2026-10-20"},
        "project": {"id": 1, "name": "meute"},
        "repo_id": None,
        "version": 2,
        "created_at": "2026-10-15T08:00:00Z",
        "updated_at": "2026-10-15T08:00:00Z",
        "completed_at": None,
    }


def test_due_json_round_trips_and_rejects_other_shapes() -> None:
    at = DueAt(at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC))
    assert due_to_json(at) == {"kind": "at", "value": "2026-10-20T12:00:00Z"}
    for due in (date_due("2026-10-20"), at):
        assert due_from_json(due_to_json(due)) == due
    for bad in (
        {"kind": "week", "value": "x"},
        {"kind": "date"},
        {"kind": "date", "value": "2026-02-30"},
    ):
        with pytest.raises(InvalidInput):
            due_from_json(bad)


def test_due_at_is_aware_and_normalised_to_utc() -> None:
    assert at_due("2026-10-14T18:00[Europe/Paris]").at == datetime(2026, 10, 14, 16, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="naive"):
        DueAt(at=datetime(2026, 10, 14, 18, 0))  # noqa: DTZ001 — the naive value is the point


def test_task_label_has_hash() -> None:
    assert task_label(TaskId(12)) == "#12"
