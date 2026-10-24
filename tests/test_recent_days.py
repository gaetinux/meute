"""The `ui.recent_days` setting: how long ended sessions stay on the board."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from meute.cli.board_data import recent_ended_sessions, recently_ended
from meute.cli.config_edit import config_set
from meute.cli.context import CliContext
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config, config_get, load_config
from meute.core.config_validate import UiConfig
from meute.core.db.connection import Database
from meute.core.db.sessions import create_session, set_session_state
from meute.core.errors import InvalidInput
from meute.core.paths import Paths
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Exited, Running
from support import FIXED

OLD = SessionId("aaaa1111-0000-4000-8000-000000000000")
NEWER = SessionId("aaaa2222-0000-4000-8000-000000000000")
SHELL = SessionId("aaaa3333-0000-4000-8000-000000000000")


def _new(session_id: SessionId, agent: AgentKind) -> NewSession:
    return NewSession(
        id=session_id, agent=agent, title=str(session_id)[:4], cwd=Path("/work"), state=Running()
    )


def _ctx(db: Database, tmp_path: Path, days: int) -> CliContext:
    return CliContext(
        db=db,
        now=FIXED,
        actor=Actor(author=Author.USER, channel=Channel.CLI),
        config=Config(ui=UiConfig(recent_days=days)),
        paths=Paths.from_env({"XDG_STATE_HOME": str(tmp_path)}, home=tmp_path),
    )


def _db_with_ended(holder: list[datetime]) -> Database:
    """Open a database where OLD ended 8 days and NEWER 1 day before FIXED + 8 days."""
    db = Database.in_memory(clock=lambda: holder[0])
    create_session(db, _new(OLD, AgentKind.CLAUDE))
    create_session(db, _new(NEWER, AgentKind.CLAUDE))
    create_session(db, _new(SHELL, AgentKind.BASH))
    set_session_state(db, OLD, Exited(code=0))
    set_session_state(db, SHELL, Exited(code=0))
    holder[0] = FIXED + timedelta(days=7)
    set_session_state(db, NEWER, Exited(code=0))
    holder[0] = FIXED + timedelta(days=8)
    return db


def test_recent_days_defaults_to_seven(tmp_path: Path) -> None:
    path = tmp_path / "absent.toml"
    assert Config().ui.recent_days == 7
    assert config_get(path, "ui.recent_days") == "7"


def test_config_set_accepts_and_rereads(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"
    config_set(path, "ui.recent_days", "14")
    assert config_get(path, "ui.recent_days") == "14"
    assert load_config(path).ui.recent_days == 14


@pytest.mark.parametrize("value", ["0", "366", "x"])
def test_config_set_refuses_out_of_range(tmp_path: Path, value: str) -> None:
    path = tmp_path / "c.toml"
    with pytest.raises(InvalidInput):
        config_set(path, "ui.recent_days", value)


@pytest.mark.parametrize("value", ["1", "365"])
def test_bounds_are_inclusive(tmp_path: Path, value: str) -> None:
    path = tmp_path / "c.toml"
    config_set(path, "ui.recent_days", value)
    assert config_get(path, "ui.recent_days") == value


@pytest.mark.parametrize(("days", "expected"), [(7, {NEWER}), (14, {OLD, NEWER})])
def test_board_shows_sessions_ended_within_recent_days(
    tmp_path: Path, days: int, expected: set[SessionId]
) -> None:
    holder = [FIXED]
    with _db_with_ended(holder) as db:
        ctx = _ctx(db, tmp_path, days)
        ids = {row.session.id for row in recently_ended(ctx, (), holder[0])}
    assert ids - {SHELL} == expected


def test_recent_ended_sessions_are_claude_only_most_recent_first(tmp_path: Path) -> None:
    holder = [FIXED]
    with _db_with_ended(holder) as db:
        ctx = _ctx(db, tmp_path, 14)
        assert [s.id for s in recent_ended_sessions(ctx, holder[0])] == [NEWER, OLD]
        ctx = _ctx(db, tmp_path, 7)
        assert [s.id for s in recent_ended_sessions(ctx, holder[0])] == [NEWER]


def test_recent_ended_sessions_skip_live_ones(tmp_path: Path) -> None:
    with Database.in_memory(clock=lambda: FIXED) as db:
        create_session(db, _new(OLD, AgentKind.CLAUDE))
        assert recent_ended_sessions(_ctx(db, tmp_path, 7), FIXED) == ()
