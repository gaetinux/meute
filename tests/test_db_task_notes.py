"""Task notes."""

import pytest

from meute.core.actor import Author, Channel
from meute.core.db.connection import Database
from meute.core.db.task_notes import add_note, notes
from meute.core.db.tasks import create_task, get_task
from meute.core.errors import InvalidInput, NotFound
from meute.core.task import TaskId
from support import CLAUDE, USER, new_task


def test_notes_do_not_bump_version_and_keep_author(db: Database) -> None:
    t = create_task(db, new_task("Review the PR"), USER)
    note = add_note(db, t.id, "  Done with the SQL part ", CLAUDE)
    assert (note.body, note.author, note.channel, note.session_id) == (
        "Done with the SQL part",
        Author.CLAUDE,
        Channel.MCP,
        "s-1",
    )
    assert get_task(db, t.id).version == 1
    assert notes(db, t.id) == [note]


def test_blank_note_and_missing_task_are_rejected(db: Database) -> None:
    t = create_task(db, new_task("Review the PR"), USER)
    with pytest.raises(InvalidInput, match=r"^note cannot be empty$"):
        add_note(db, t.id, "  ", USER)
    with pytest.raises(NotFound):
        add_note(db, TaskId(9), "x", USER)
