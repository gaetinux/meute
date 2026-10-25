"""The start-up purge also drops old session events, and never blocks the dashboard."""

import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from meute.cli import app
from meute.core.db.claude_sessions import purge_samples
from meute.core.db.connection import Database
from meute.core.db.rows import fetch_all, fetch_one
from meute.core.db.sessions import create_session
from meute.core.errors import MeuteError
from meute.core.instants import to_db
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from support import FIXED

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")
NOW = FIXED + timedelta(days=100)
LIMIT = NOW - timedelta(days=30)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    with Database.open(tmp_path / "m.db", busy_timeout_ms=1000, clock=lambda: FIXED) as opened:
        create_session(
            opened,
            NewSession(id=SID, agent=AgentKind.CLAUDE, title="c", cwd=Path("/w"), state=Running()),
        )
        yield opened


def _event(db: Database, name: str, days_old: float) -> None:
    db.conn.execute(
        "INSERT INTO session_events (session_id, event, detail, created_at) VALUES (?, ?, ?, ?)",
        (SID, name, "d", to_db(NOW - timedelta(days=days_old))),
    )


def _names(db: Database) -> list[str]:
    rows = fetch_all(db.conn, "SELECT event FROM session_events ORDER BY event")
    return [str(row[0]) for row in rows]


def test_events_older_than_the_limit_are_deleted_newer_kept(db: Database) -> None:
    _event(db, "old", 31)
    _event(db, "recent", 29)
    assert purge_samples(db, older_than=LIMIT) == 1
    assert _names(db) == ["recent"]


def test_an_event_exactly_at_the_limit_is_kept(db: Database) -> None:
    _event(db, "edge", 30)
    assert purge_samples(db, older_than=LIMIT) == 0
    assert _names(db) == ["edge"]


def test_the_total_counts_metrics_quotas_and_events(db: Database) -> None:
    stamp = to_db(NOW - timedelta(days=40))
    db.conn.execute(
        "INSERT INTO metric_samples (session_id, created_at) VALUES (?, ?)", (SID, stamp)
    )
    db.conn.execute("INSERT INTO quota_samples (created_at) VALUES (?)", (stamp,))
    _event(db, "old", 40)
    assert purge_samples(db, older_than=LIMIT) == 3


def test_the_session_itself_remains(db: Database) -> None:
    _event(db, "old", 40)
    assert purge_samples(db, older_than=LIMIT) == 1
    row = fetch_one(db.conn, "SELECT count(*) FROM sessions")
    assert row is not None
    assert row[0] == 1


class _FakeBackend:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def close(self) -> None:
        self._calls.append("close")


class _FakeApp:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def run(self) -> None:
        self._calls.append("run")


@pytest.mark.parametrize(
    "failure", [sqlite3.OperationalError("database is locked"), MeuteError("boom")]
)
def test_a_failing_purge_does_not_keep_the_dashboard_from_starting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    calls: list[str] = []
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    def scan(*_: object) -> None:
        calls.append("scan")

    def purge(*_: object, **__: object) -> int:
        raise failure

    def app_factory(*_: object) -> _FakeApp:
        return _FakeApp(calls)

    def backend(*_: object) -> _FakeBackend:
        return _FakeBackend(calls)

    def tmux_env(*_: object) -> None:
        return None

    monkeypatch.setattr("meute.cli.open_tmux_env", tmux_env)
    monkeypatch.setattr("meute.cli.repo_scan.scan_repos", scan)
    monkeypatch.setattr("meute.cli.board_backend.purge_samples", purge)
    monkeypatch.setattr("meute.cli.board_backend.CliBoardBackend", backend)
    monkeypatch.setattr("meute.tui.board.BoardApp", app_factory)
    assert CliRunner().invoke(app, ["board"]).exit_code == 0
    assert calls == ["scan", "run", "close"]
