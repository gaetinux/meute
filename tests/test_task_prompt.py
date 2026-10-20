"""Tests of the text pasted into Claude for a task."""

from dataclasses import replace
from datetime import UTC, datetime

from meute.core.actor import Author, Channel
from meute.core.task import Note, TaskId
from meute.core.task_prompt import task_prompt
from support import make_task


def _note(note_id: int, body: str, minute: int) -> Note:
    return Note(
        id=note_id,
        task_id=TaskId(7),
        body=body,
        author=Author.USER,
        channel=Channel.TUI,
        session_id=None,
        created_at=datetime(2026, 10, 14, 8, minute, tzinfo=UTC),
    )


def test_title_only() -> None:
    assert task_prompt(make_task(7), []) == "#7 task 7"


def test_full_text_oldest_note_first() -> None:
    task = replace(make_task(7), description="Check the tabs.\nThen the quick add.\n")
    notes = [_note(2, "second", 20), _note(1, "first", 10)]
    assert task_prompt(task, notes) == (
        "#7 task 7\n\nCheck the tabs.\nThen the quick add.\n\nNotes:\n- first\n- second"
    )


def test_notes_without_description() -> None:
    assert task_prompt(make_task(7), [_note(1, "only", 10)]) == "#7 task 7\n\nNotes:\n- only"


def test_blank_description_is_skipped() -> None:
    task = replace(make_task(7), description=" \n ")
    assert task_prompt(task, []) == "#7 task 7"


def test_no_escape_can_end_the_bracketed_paste() -> None:
    task = replace(
        make_task(7),
        title="x\x1b[201~\r",
        description="d\x1b[201~\r\nmore\x1b",
    )
    text = task_prompt(task, [_note(1, "n\x1b[201~", 10), _note(2, "y;", 20)])
    assert "\x1b" not in text
    assert "\r" not in text
    assert text.endswith("y;")
    assert text.count("\n") == 7
