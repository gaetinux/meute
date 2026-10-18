"""Tests for session identifiers and the session JSON form."""

from pathlib import Path

import pytest

from meute.core.errors import InvalidInput
from meute.core.project import ProjectId, RepoId
from meute.core.session import (
    AgentKind,
    Session,
    SessionId,
    new_session_id,
    parse_session_id,
    session_to_json,
    short_id,
)
from meute.core.session_state import Exited
from meute.core.task import TaskId
from support import FIXED


def test_parse_session_id_canonicalises_and_rejects() -> None:
    assert (
        parse_session_id("AAAA1111-0000-4000-8000-000000000000")
        == "aaaa1111-0000-4000-8000-000000000000"
    )
    with pytest.raises(InvalidInput, match=r"^invalid session id: nope$"):
        parse_session_id("nope")


@pytest.mark.parametrize(
    "text", ["aaaa1111000-0-4000-8000-000000000000", "aaaa1111000040008000000000000000"]
)
def test_parse_session_id_requires_the_hyphenated_form(text: str) -> None:
    with pytest.raises(InvalidInput, match=r"^invalid session id: "):
        parse_session_id(text)


def test_short_id_and_new_id() -> None:
    assert short_id(SessionId("aaaa1111-0000-4000-8000-000000000000")) == "aaaa1111"
    first, second = new_session_id(), new_session_id()
    assert parse_session_id(first) == first
    assert first != second


def test_session_json_has_every_field() -> None:
    session = Session(
        id=SessionId("aaaa1111-0000-4000-8000-000000000000"),
        agent=AgentKind.BASH,
        title="shell",
        project_id=ProjectId(1),
        repo_id=RepoId(2),
        task_id=TaskId(3),
        cwd=Path("/work/repo"),
        state=Exited(code=2),
        last_activity_at=FIXED,
        created_at=FIXED,
        ended_at=FIXED,
    )
    assert session_to_json(session) == {
        "id": "aaaa1111-0000-4000-8000-000000000000",
        "agent": "bash",
        "title": "shell",
        "project_id": 1,
        "repo_id": 2,
        "task_id": 3,
        "cwd": "/work/repo",
        "state": {"kind": "exited", "code": 2},
        "last_activity_at": "2026-10-14T08:30:00Z",
        "created_at": "2026-10-14T08:30:00Z",
        "ended_at": "2026-10-14T08:30:00Z",
    }
