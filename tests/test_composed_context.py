"""The composed context: rule, instructions of each level, task line."""

from datetime import UTC, datetime

from syrupy.assertion import SnapshotAssertion

from meute.core.context import (
    CONTRADICTION_RULE,
    compose_context,
    task_line,
    work_on_task_text,
)
from meute.core.project import Project, ProjectId
from meute.core.task import TaskId


def _project(instructions: str, name: str = "meute") -> Project:
    return Project(
        id=ProjectId(1),
        name=name,
        description="",
        instructions=instructions,
        created_at=datetime(2026, 10, 14, tzinfo=UTC),
    )


def test_exact_texts() -> None:
    assert CONTRADICTION_RULE == (
        "The repository's `CLAUDE.md` files are authoritative on code conventions. "
        "The task is authoritative on the goal. If they contradict each other, "
        "point it out to the user instead of choosing."
    )
    assert task_line(TaskId(7)) == (
        "You are working on task #7. Read it with the `task_read` tool "
        "and report your progress with `task_note_add`."
    )
    assert work_on_task_text(TaskId(7)) == "Work on task #7."


def test_no_level_gives_none() -> None:
    assert compose_context(global_instructions="", project=None, task_id=None) is None


def test_blank_instructions_are_omitted() -> None:
    assert (
        compose_context(global_instructions=" \n\t", project=_project("  \n"), task_id=None) is None
    )


def test_global_only(snapshot: SnapshotAssertion) -> None:
    assert compose_context(global_instructions="Be brief.", project=None, task_id=None) == snapshot


def test_project_only(snapshot: SnapshotAssertion) -> None:
    assert (
        compose_context(global_instructions="", project=_project("Use uv."), task_id=None)
        == snapshot
    )


def test_task_only(snapshot: SnapshotAssertion) -> None:
    assert compose_context(global_instructions="", project=None, task_id=TaskId(12)) == snapshot


def test_all_levels(snapshot: SnapshotAssertion) -> None:
    text = compose_context(
        global_instructions="\n  Be brief.\nAnswer in French.  \n",
        project=_project("Use uv.\n\n  Keep TDD.", name="my proj"),
        task_id=TaskId(12),
    )
    assert text == snapshot
