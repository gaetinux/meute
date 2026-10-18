"""The 30-day sample purge at dashboard start, and the backend's use of the poller."""

from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from meute.cli import app
from meute.cli.board_backend import purge_old_samples
from meute.cli.context import CliContext
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.db.rows import as_integer, fetch_one
from meute.core.db.samples import record_metrics
from meute.core.db.sessions import create_session
from meute.core.paths import Paths
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from meute.core.statusline import parse_statusline
from support import FIXED, claude_statusline_fixture

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")


def _count(db: Database) -> int:
    row = fetch_one(db.conn, "SELECT COUNT(*) FROM metric_samples")
    assert row is not None
    return as_integer(row[0])


def test_old_samples_are_purged_recent_kept(tmp_path: Path) -> None:
    data = parse_statusline(claude_statusline_fixture("statusline-2"))
    clock = [FIXED]
    with Database.open(tmp_path / "m.db", busy_timeout_ms=1000, clock=lambda: clock[0]) as db:
        create_session(
            db,
            NewSession(id=SID, agent=AgentKind.CLAUDE, title="c", cwd=Path("/w"), state=Running()),
        )
        assert record_metrics(db, SID, data)
        clock[0] = FIXED + timedelta(days=20)
        assert record_metrics(db, SID, data)
        now = FIXED + timedelta(days=40)
        ctx = CliContext(
            db=db,
            now=now,
            actor=Actor(author=Author.USER, channel=Channel.CLI),
            config=Config(),
            paths=Paths.from_env({"XDG_STATE_HOME": str(tmp_path)}, home=tmp_path),
        )
        assert _count(db) == 2
        assert purge_old_samples(ctx) == 1
        assert _count(db) == 1


class _FakeApp:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def run(self) -> None:
        self._calls.append("run")


def test_board_command_purges_at_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    def scan(*_: object) -> None:
        calls.append("scan")

    def purge(*_: object, **__: object) -> int:
        calls.append("purge")
        return 0

    def app_factory(*_: object) -> _FakeApp:
        return _FakeApp(calls)

    def backend(*_: object) -> None:
        return None

    def tmux_env(*_: object) -> None:
        return None

    monkeypatch.setattr("meute.cli.open_tmux_env", tmux_env)
    monkeypatch.setattr("meute.cli.repo_scan.scan_repos", scan)
    monkeypatch.setattr("meute.cli.board_backend.purge_samples", purge)
    monkeypatch.setattr("meute.cli.board_backend.CliBoardBackend", backend)
    monkeypatch.setattr("meute.tui.board.BoardApp", app_factory)
    assert CliRunner().invoke(app, ["board"]).exit_code == 0
    assert calls == ["scan", "purge", "run"]
