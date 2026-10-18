"""Tests for the small shared helpers extracted after the plan 3 review."""

from pathlib import Path

import pytest

from meute.core.claude_session import ClaudeDetails
from meute.core.db.claude_sessions import claude_details_by_session
from meute.core.db.connection import Database
from meute.core.db.rows import as_real
from meute.core.db.schema import SCHEMA_VERSION, current_version
from meute.core.db.sessions import create_session
from meute.core.json_types import parse_json_object
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from meute.core.text import one_line

CLAUDE = SessionId("aaaa1111-0000-4000-8000-000000000000")
BASH = SessionId("aaaa2222-0000-4000-8000-000000000000")


def test_as_real_accepts_numbers() -> None:
    assert as_real(3) == 3.0
    assert isinstance(as_real(3), float)
    assert as_real(2.5) == 2.5


@pytest.mark.parametrize("value", [True, "1.5", None])
def test_as_real_rejects_other_types(value: object) -> None:
    with pytest.raises(ValueError, match=r"^corrupt row: expected number, got "):
        as_real(value)


def test_one_line_collapses_whitespace_and_neutralises_controls() -> None:
    assert one_line("a \n\t b\x1b[0m", 50) == "a b�[0m"


def test_one_line_cuts_to_the_limit() -> None:
    assert one_line("abcdef", 4) == "abcd"
    assert one_line("abcd", 4) == "abcd"


def test_one_line_ellipsis_keeps_room_for_the_mark() -> None:
    assert one_line("abcdef", 4, ellipsis=True) == "abc…"
    assert one_line("abcd", 4, ellipsis=True) == "abcd"


def test_parse_json_object_keeps_string_keys() -> None:
    assert parse_json_object('{"a": 1, "b": [true]}') == {"a": 1, "b": [True]}


@pytest.mark.parametrize("text", ["[1]", "3", "null", "{", ""])
def test_parse_json_object_rejects_anything_else(text: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 — JSONDecodeError is a ValueError too
        parse_json_object(text)


def test_current_version_is_the_schema_version() -> None:
    assert current_version(Database.in_memory().conn) == SCHEMA_VERSION


def test_claude_details_by_session_lists_claude_sessions_only() -> None:
    db = Database.in_memory()
    for session_id, agent in ((CLAUDE, AgentKind.CLAUDE), (BASH, AgentKind.BASH)):
        create_session(
            db,
            NewSession(id=session_id, agent=agent, title="t", cwd=Path("/work"), state=Running()),
        )
    db.conn.execute("UPDATE sessions SET native_id = 'n1', model = 'm' WHERE id = ?", (CLAUDE,))
    assert claude_details_by_session(db) == {CLAUDE: ClaudeDetails(native_id="n1", model="m")}
