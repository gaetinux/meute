"""Tests that kill the mutants plan 6b left alive (docs/dev/mutants/2026-plan-6b-python.md)."""

from dataclasses import replace

import pytest

from meute.core.db.connection import Database
from meute.core.db.saved_states import delete_state, get_state
from meute.core.errors import NotFound
from meute.core.project import RepoId
from meute.core.saved_state import (
    parse_sessions,
    reopening_text,
    saved_text,
    sessions_json,
)
from meute.core.session import AgentKind, SessionId
from meute.core.task import TaskId
from support import FIXED, saved_session

# --- meute.core.saved_state


def test_saved_and_reopening_texts_name_the_state() -> None:
    assert saved_text("review") == "state saved: review"
    assert reopening_text("review") == "reopening review…"


def test_saved_and_reopening_texts_neutralise_control_characters() -> None:
    assert saved_text("a\x1bb") == "state saved: a�b"
    assert reopening_text("a\x1bb") == "reopening a�b…"


_ENTRY = saved_session(
    SessionId("aaaa1111-0000-4000-8000-000000000000"),
    title="t",
    agent=AgentKind.CLAUDE,
    native_id="native-1",
    task_id=TaskId(2**63 - 1),
    repo_id=RepoId(2**63 - 1),
)


def test_the_largest_database_id_is_read() -> None:
    assert parse_sessions(sessions_json((_ENTRY,))) == (_ENTRY,)


def test_ids_of_one_are_read() -> None:
    entry = replace(_ENTRY, task_id=TaskId(1), repo_id=RepoId(1))
    assert parse_sessions(sessions_json((entry,))) == (entry,)


# --- meute.core.db.saved_states


def _check(caught: pytest.ExceptionInfo[NotFound]) -> None:
    assert (caught.value.entity, caught.value.ident) == ("saved state", "nope")
    assert str(caught.value) == "no saved state named nope"


def test_getting_an_unknown_state_names_its_entity_and_ident() -> None:
    db = Database.in_memory(clock=lambda: FIXED)
    with pytest.raises(NotFound) as caught:
        _ = get_state(db, "nope")
    _check(caught)


def test_deleting_an_unknown_state_names_its_entity_and_ident() -> None:
    db = Database.in_memory(clock=lambda: FIXED)
    with pytest.raises(NotFound) as caught:
        delete_state(db, "nope")
    _check(caught)
