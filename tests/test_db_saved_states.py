"""The `saved_states` table: saving with retention, listing, reading and removing."""

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.migrations import MIGRATIONS, migrate
from meute.core.db.rows import fetch_all, fetch_one
from meute.core.db.saved_states import delete_state, get_state, list_states, save_state
from meute.core.errors import NotFound
from meute.core.instants import to_db
from meute.core.saved_state import LAST, RETAINED, SavedSession, SavedState
from meute.core.session import AgentKind, SessionId
from support import FIXED

SHELL = SavedSession(
    session_id=SessionId("aaaa1111-0000-4000-8000-000000000000"),
    agent=AgentKind.BASH,
    cwd=Path("/work"),
    native_id=None,
    title="shell",
    task_id=None,
    repo_id=None,
    displayed=True,
)


class Clock:
    """A clock that moves one minute forward at each reading."""

    def __init__(self) -> None:
        self.at = FIXED

    def __call__(self) -> datetime:
        self.at += timedelta(minutes=1)
        return self.at


class BackwardsClock:
    """A clock that moves one minute back at each reading, as after a clock change."""

    def __init__(self) -> None:
        self.at = FIXED

    def __call__(self) -> datetime:
        self.at -= timedelta(minutes=1)
        return self.at


def _names(db: Database) -> list[str]:
    return [state.name for state in list_states(db)]


def test_an_empty_database_gets_the_table() -> None:
    with Database.in_memory() as db:
        assert fetch_all(db.conn, "SELECT * FROM saved_states") == []


def test_migrating_a_v4_file_adds_the_table_and_backs_it_up(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, MIGRATIONS[:4])
        conn.execute(
            "INSERT INTO tasks (title, status, priority, version, created_at, updated_at)"
            " VALUES ('keep me', 'todo', 'normal', 1, 'x', 'x')"
        )
    with Database.open(path, busy_timeout_ms=1000) as db:
        assert db.schema_version() == len(MIGRATIONS) == 5
        assert fetch_one(db.conn, "SELECT title FROM tasks") == ("keep me",)
        assert fetch_all(db.conn, "SELECT * FROM saved_states") == []
    assert (tmp_path / "meute.db.bak-4").exists()


def test_names_are_unique(db: Database) -> None:
    db.conn.execute("INSERT INTO saved_states (name, created_at, sessions) VALUES ('a', 'x', '[]')")
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute(
            "INSERT INTO saved_states (name, created_at, sessions) VALUES ('a', 'y', '[]')"
        )


def test_save_then_get(db: Database) -> None:
    saved = save_state(db, "work", (SHELL,))
    assert saved == SavedState(name="work", created_at=FIXED, sessions=(SHELL,))
    assert get_state(db, "work") == saved
    assert fetch_one(db.conn, "SELECT created_at FROM saved_states") == (to_db(FIXED),)


def test_eleven_saves_keep_ten_named_states_and_last(db: Database) -> None:
    save_state(db, LAST, (SHELL,))
    for index in range(RETAINED + 1):
        save_state(db, f"s{index}", ())
    assert _names(db) == [LAST, *(f"s{index}" for index in range(RETAINED, 0, -1))]


def test_retention_drops_the_oldest_save() -> None:
    clock = Clock()
    with Database.in_memory(clock=clock) as db:
        save_state(db, "oldest", ())
        for index in range(RETAINED - 1):
            save_state(db, f"s{index}", ())
        save_state(db, "oldest", ())  # renewed: now the newest
        save_state(db, "extra", ())
        names = _names(db)
    assert len(names) == RETAINED
    assert names[:2] == ["extra", "oldest"]
    assert "s0" not in names


def test_saving_last_drops_nothing(db: Database) -> None:
    for index in range(RETAINED):
        save_state(db, f"s{index}", ())
    save_state(db, LAST, ())
    assert len(_names(db)) == RETAINED + 1


def test_saving_under_the_same_name_replaces_the_state_and_moves_it_up() -> None:
    clock = Clock()
    with Database.in_memory(clock=clock) as db:
        first = save_state(db, "a", ())
        save_state(db, "b", ())
        renewed = save_state(db, "a", (SHELL,))
        assert _names(db) == ["a", "b"]
        assert renewed.created_at > first.created_at
        assert get_state(db, "a") == renewed
        assert renewed.sessions == (SHELL,)
        assert fetch_one(db.conn, "SELECT count(*) FROM saved_states") == (2,)


def test_saving_last_again_replaces_it(db: Database) -> None:
    save_state(db, LAST, ())
    save_state(db, LAST, (SHELL,))
    assert list_states(db) == (SavedState(name=LAST, created_at=FIXED, sessions=(SHELL,)),)


def test_list_puts_last_first_then_the_newest() -> None:
    clock = Clock()
    with Database.in_memory(clock=clock) as db:
        save_state(db, "old", ())
        save_state(db, LAST, ())
        save_state(db, "mid", ())
        save_state(db, "new", ())
        assert _names(db) == [LAST, "new", "mid", "old"]


def test_list_breaks_ties_by_save_order(db: Database) -> None:
    for name in ("b", "a", "c"):
        save_state(db, name, ())
    assert _names(db) == ["c", "a", "b"]


def test_list_follows_the_save_order_when_the_clock_goes_back() -> None:
    with Database.in_memory(clock=BackwardsClock()) as db:
        save_state(db, "first", ())
        save_state(db, LAST, ())
        save_state(db, "second", ())
        save_state(db, "third", ())
        assert _names(db) == [LAST, "third", "second", "first"]


def test_retention_keeps_the_latest_saves_when_the_clock_goes_back() -> None:
    with Database.in_memory(clock=BackwardsClock()) as db:
        save_state(db, LAST, ())
        for index in range(RETAINED + 1):
            save_state(db, f"s{index}", ())
        assert _names(db) == [LAST, *(f"s{index}" for index in range(RETAINED, 0, -1))]


def test_list_of_an_empty_table(db: Database) -> None:
    assert list_states(db) == ()


def test_unreadable_sessions_give_an_empty_state(db: Database) -> None:
    db.conn.execute(
        "INSERT INTO saved_states (name, created_at, sessions) VALUES ('bad', ?, 'not json')",
        (to_db(FIXED),),
    )
    assert get_state(db, "bad").sessions == ()


def test_delete(db: Database) -> None:
    save_state(db, "a", ())
    save_state(db, "b", ())
    delete_state(db, "a")
    assert _names(db) == ["b"]


def test_get_an_unknown_name_is_not_found(db: Database) -> None:
    save_state(db, "a", ())
    with pytest.raises(NotFound) as caught:
        get_state(db, "nope")
    assert str(caught.value) == "no saved state named nope"


def test_delete_an_unknown_name_is_not_found(db: Database) -> None:
    save_state(db, "a", ())
    with pytest.raises(NotFound) as caught:
        delete_state(db, "nope")
    assert str(caught.value) == "no saved state named nope"
    assert _names(db) == ["a"]
