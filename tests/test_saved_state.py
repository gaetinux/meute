"""The saved-state model: its JSON, its names and its texts."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from meute.core.saved_state import (
    LAST,
    NAME_LIMIT,
    RETAINED,
    SavedSession,
    SavedState,
    parse_sessions,
    reopen_text,
    sessions_json,
    stamp_name,
    state_line,
    state_name,
)
from syrupy.assertion import SnapshotAssertion

from meute.core.errors import InvalidInput
from meute.core.project import RepoId
from meute.core.session import AgentKind, SessionId
from meute.core.task import TaskId

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")
BASH_SID = SessionId("bbbb2222-0000-4000-8000-000000000000")
NOW = datetime(2026, 10, 24, 9, 12, tzinfo=UTC)

CLAUDE = SavedSession(
    session_id=SID,
    agent=AgentKind.CLAUDE,
    cwd=Path("/work/meute"),
    native_id="native-1",
    title="fix the board",
    task_id=TaskId(12),
    repo_id=RepoId(3),
    displayed=True,
)
BASH = SavedSession(
    session_id=BASH_SID,
    agent=AgentKind.BASH,
    cwd=Path("/work/other"),
    native_id=None,
    title="shell",
    task_id=None,
    repo_id=None,
    displayed=False,
)


def test_constants() -> None:
    assert (LAST, RETAINED, NAME_LIMIT) == ("last", 10, 60)


def test_sessions_json_is_a_compact_array(snapshot: SnapshotAssertion) -> None:
    assert sessions_json((CLAUDE, BASH)) == snapshot


_CLAUDE_ENTRY: dict[str, object] = {
    "session_id": SID,
    "agent": "claude",
    "cwd": "/work/meute",
    "native_id": "native-1",
    "title": "fix the board",
    "task_id": 12,
    "repo_id": 3,
    "displayed": True,
}


def _entry(**changes: object) -> str:
    return json.dumps({**_CLAUDE_ENTRY, **changes})


def test_parse_reads_an_entry() -> None:
    assert parse_sessions(f"[{_entry()}]") == (CLAUDE,)


def test_parse_keeps_valid_entries_and_skips_invalid_ones() -> None:
    no_cwd = {key: value for key, value in _CLAUDE_ENTRY.items() if key != "cwd"}
    text = (
        f"[{_entry(agent='zsh')}, {json.dumps(no_cwd)},"
        f" {_entry(session_id=SID.upper())}, {sessions_json((BASH,))[1:-1]}]"
    )
    assert parse_sessions(text) == (BASH,)


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"cwd": "relative/dir"}, id="relative-cwd"),
        pytest.param({"cwd": ""}, id="empty-cwd"),
        pytest.param({"session_id": "not-a-uuid"}, id="bad-id"),
        pytest.param({"session_id": SID.replace("-", "")}, id="unhyphenated-id"),
        pytest.param({"task_id": True}, id="bool-task"),
        pytest.param({"task_id": 1.0}, id="float-task"),
        pytest.param({"task_id": 2**63}, id="huge-task"),
        pytest.param({"repo_id": 0}, id="zero-repo"),
        pytest.param({"repo_id": "3"}, id="text-repo"),
        pytest.param({"native_id": 1}, id="number-native"),
        pytest.param({"title": None}, id="no-title"),
        pytest.param({"displayed": 1}, id="number-displayed"),
    ],
)
def test_parse_skips_an_entry_with_a_wrong_field(changes: dict[str, object]) -> None:
    assert parse_sessions(f"[{_entry(**changes)}]") == ()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "{}",
        '{"sessions": []}',
        "null",
        '[1, null, [], "x"]',
        "[" * 100_000 + "]" * 100_000,
        "[" + "9" * 5000 + "]",
    ],
)
def test_parse_an_unreadable_document_gives_nothing(text: str) -> None:
    assert parse_sessions(text) == ()


_ids = st.uuids().map(lambda value: SessionId(str(value)))
_paths = st.lists(st.text(alphabet=st.characters(exclude_characters="/"), max_size=8)).map(
    lambda parts: Path("/", *parts)
)
_db_ids = st.integers(1, 2**63 - 1)
_saved = st.builds(
    SavedSession,
    session_id=_ids,
    agent=st.sampled_from(AgentKind),
    cwd=_paths,
    native_id=st.none() | st.text(),
    title=st.text(),
    task_id=st.none() | _db_ids.map(TaskId),
    repo_id=st.none() | _db_ids.map(RepoId),
    displayed=st.booleans(),
)


@given(st.lists(_saved, max_size=5).map(tuple))
def test_json_round_trip(sessions: tuple[SavedSession, ...]) -> None:
    assert parse_sessions(sessions_json(sessions)) == sessions


@given(st.text(max_size=300))
def test_parse_never_raises_on_text(text: str) -> None:
    parse_sessions(text)


_json = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=20),
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=12), inner),
    max_leaves=20,
)
_keys = st.sampled_from(
    ["session_id", "agent", "cwd", "native_id", "title", "task_id", "repo_id", "displayed"]
)


@given(st.lists(st.dictionaries(_keys, _json)) | _json)
def test_parse_never_raises_on_json(document: object) -> None:
    parse_sessions(json.dumps(document))


def test_state_name_cuts_at_the_limit() -> None:
    assert state_name("x" * 61) == "x" * 60


def test_state_name_puts_the_text_on_one_line() -> None:
    assert state_name("  a\nb  ") == "a b"


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_state_name_refuses_an_empty_name(text: str) -> None:
    with pytest.raises(InvalidInput, match=r"^state name is empty$"):
        state_name(text)


@pytest.mark.parametrize("text", ["last", "  last "])
def test_state_name_refuses_last(text: str) -> None:
    with pytest.raises(InvalidInput, match=r"^last is kept by the board$"):
        state_name(text)


def test_state_name_compares_last_as_is() -> None:
    assert state_name("LAST") == "LAST"


def test_stamp_name() -> None:
    assert stamp_name(datetime(2026, 10, 24, 9, 12, 59, tzinfo=UTC)) == "2026-10-24 09:12"


def test_reopen_text() -> None:
    skipped = [("fix the board", "already running"), ("shell", "folder not found: /gone")]
    assert reopen_text(2, skipped) == [
        "reopened 2 · skipped 2",
        "  fix the board: already running",
        "  shell: folder not found: /gone",
    ]
    assert reopen_text(0, []) == ["reopened 0 · skipped 0"]


def test_reopen_text_neutralises_control_characters() -> None:
    assert reopen_text(0, [("a\x1b[2Jb", "c\nd")])[1] == "  a�[2Jb: c�d"


def _state(name: str, count: int, age: timedelta) -> SavedState:
    return SavedState(name=name, created_at=NOW - age, sessions=(BASH,) * count)


def test_state_line() -> None:
    assert state_line(_state("2026-10-24 09:12", 3, timedelta(hours=2)), NOW) == (
        "2026-10-24 09:12  3 sessions  2h"
    )
    assert state_line(_state("work", 1, timedelta(0)), NOW) == "work  1 session  now"
    assert state_line(_state("empty", 0, timedelta(days=3)), NOW) == "empty  0 sessions  3d"


def test_state_line_neutralises_the_name() -> None:
    assert state_line(_state("a\x1bb", 1, timedelta(0)), NOW) == "a�b  1 session  now"
