"""Tests added after mutmut: plan 4 behaviour that earlier tests left unchecked."""

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from meute.core.agents import AgentInfo
from meute.core.attention import next_attention
from meute.core.board_sessions import board_sessions, line_entry
from meute.core.board_view import LaunchBash, SessionEntry, SessionRow, new_action, stopping_text
from meute.core.config_validate import QuotasConfig
from meute.core.db.connection import Database
from meute.core.project import RepoId
from meute.core.quota_view import QuotaLine, projected_limit, quota_lines
from meute.core.session import Session, SessionId
from meute.core.session_state import (
    Exited,
    Idle,
    MaybeStuck,
    PermissionRequested,
    Running,
    SessionState,
    WaitingInput,
)
from meute.core.sessions_view import (
    InfoLine,
    RepoLine,
    SessionInfo,
    SessionLine,
    SessionsView,
    ViewState,
    build_view,
)
from meute.core.statusline_render import peak_text
from support import BOARD_HOME, BOARD_ID_A, board_data, board_session


def test_an_existing_database_file_is_not_opened_by_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "meute.db"
    Database.open(path, busy_timeout_ms=1000).conn.close()
    path.chmod(0o644)
    real_open = os.open
    opened: list[str] = []

    def spy(target: str | os.PathLike[str], *args: int) -> int:
        opened.append(os.fspath(target))
        return real_open(target, *args)

    monkeypatch.setattr(os, "open", spy)
    Database.open(path, busy_timeout_ms=1000).conn.close()
    assert str(path) not in opened
    assert path.stat().st_mode & 0o777 == 0o600


# --- plan 4 : attention, Sessions view, quota -------------------------------------------------

KATHMANDU = ZoneInfo("Asia/Kathmandu")  # +05:45: no machine runs in it by accident
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)


def _at(minutes: float) -> datetime:
    return NOW + timedelta(minutes=minutes)


def _sessions(*states: SessionState) -> list[Session]:
    ids = [SessionId(f"{n:08d}-aaaa-4aaa-8aaa-aaaaaaaaaaaa") for n in range(len(states))]
    return [
        replace(board_session(i, f"s{i}", Path("/w"), None, exited=False), state=state)
        for i, state in zip(ids, states, strict=True)
    ]


def test_unknown_current_starts_at_the_first_going_forwards() -> None:
    order = _sessions(WaitingInput(), PermissionRequested(), MaybeStuck())
    assert next_attention(order, None) == order[0]


def test_unknown_current_starts_at_the_last_going_backwards() -> None:
    order = _sessions(WaitingInput(), PermissionRequested(), MaybeStuck())
    assert next_attention(order, None, backwards=True) == order[2]


def test_no_sessions_are_dated_at_the_epoch() -> None:
    data = replace(board_data(), sessions=(), ended=(), now=None)
    assert board_sessions(data, ViewState()).now == datetime(1970, 1, 1, tzinfo=UTC)


def test_board_sessions_keeps_the_given_clock() -> None:
    data = replace(board_data(), now=NOW)
    assert board_sessions(data, ViewState()).now == NOW


def test_outside_agents_and_orphans_are_in_the_view_with_a_short_home() -> None:
    agent = AgentInfo(
        pid=1,
        cwd=str(BOARD_HOME / "git" / "x"),
        kind="interactive",
        session_id="x",
        name="alone",
        status="busy",
    )
    data = replace(board_data(), outside=(agent,), orphans=("%7",))
    texts = [line.text for line in board_sessions(data, ViewState()).view.lines]
    assert "alone  busy  ~/git/x" in texts
    assert "%7" in texts


def test_a_session_line_without_its_session_has_no_entry() -> None:
    line = SessionLine(
        session_id=SessionId("ffffffff-aaaa-4aaa-8aaa-aaaaaaaaaaaa"), text="t", attention=False
    )
    board = replace(
        board_sessions(board_data(), ViewState()), infos={}, view=SessionsView(lines=(line,))
    )
    assert line_entry(board, 0) is None


def test_a_repo_line_without_its_repository_has_no_entry() -> None:
    board = replace(
        board_sessions(board_data(), ViewState()),
        view=SessionsView(lines=(RepoLine(repo_id=RepoId(99), text="t"),)),
    )
    assert line_entry(board, 0) is None


def test_new_action_on_a_session_keeps_its_repository() -> None:
    session = board_session(BOARD_ID_A, "t", Path("/w/x"), RepoId(4), exited=False)
    entry = SessionEntry(row=SessionRow(session=session, has_pane=True, displayed=False))
    assert new_action(entry) == LaunchBash(cwd=Path("/w/x"), repo_id=RepoId(4))


def test_stopping_text_neutralises_control_characters() -> None:
    assert stopping_text("a\x1b[31mb") == 'Stopping "a�[31mb"…'


def test_a_drop_between_the_first_two_samples_starts_a_new_cycle() -> None:
    samples = [(_at(-20), 50.0), (_at(-10), 10.0), (_at(0), 20.0)]
    assert projected_limit(samples, resets_at=None, now=NOW) == _at(80)


def test_equal_samples_are_not_a_drop() -> None:
    samples = [(_at(-20), 30.0), (_at(-10), 30.0), (_at(0), 40.0)]
    limit = projected_limit(samples, resets_at=None, now=NOW)
    assert limit is not None
    assert (limit - NOW).total_seconds() / 60 == pytest.approx(10 / 3 * 37, abs=0.01)


def test_a_sample_exactly_thirty_minutes_old_counts() -> None:
    samples = [(_at(-30), 40.0), (_at(0), 50.0)]
    assert projected_limit(samples, resets_at=None, now=NOW) == _at(150)


def test_a_limit_exactly_at_the_reset_is_none() -> None:
    samples = [(_at(-20), 40.0), (_at(0), 50.0)]
    assert projected_limit(samples, resets_at=_at(100), now=NOW) is None


def test_quota_lines_show_every_time_in_the_given_zone() -> None:
    line = QuotaLine(
        five_hour_pct=40.0,
        five_hour_resets_at=datetime(2026, 10, 14, 12, 0, tzinfo=UTC),
        seven_day_pct=20.0,
        seven_day_resets_at=datetime(2026, 10, 16, 12, 0, tzinfo=UTC),
        limit_at=datetime(2026, 10, 14, 11, 0, tzinfo=UTC),
        peak="",
    )
    assert quota_lines(line, local=KATHMANDU) == [
        "5h 40% · resets 17:45 · limit around 16:45 at this rate",
        "7d 20% · resets Fri 17:45",
    ]


def test_peak_text_converts_the_start_to_the_given_zone() -> None:
    now = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)  # Wednesday 15:00 in New York, after the peak
    assert peak_text(now, QuotasConfig(), KATHMANDU) == "✦ OFF-PEAK (until 17h)"


def _infos(*states: SessionState) -> list[SessionInfo]:
    return [
        SessionInfo(
            row=SessionRow(session=s, has_pane=True, displayed=False),
            details=None,
            metrics=None,
            group="g",
        )
        for s in _sessions(*states)
    ]


def _session_titles(infos: list[SessionInfo], state: ViewState) -> list[str]:
    view = build_view(infos, [], [], [], state, now=NOW, home=None)
    return [line.text for line in view.lines if isinstance(line, SessionLine)]


def test_attention_filter_skips_one_session_and_keeps_the_next() -> None:
    infos = _infos(Idle(), PermissionRequested())
    assert len(_session_titles(infos, ViewState(attention_only=True))) == 1


def test_ended_sessions_do_not_hide_the_live_ones_after_them() -> None:
    infos = _infos(Exited(code=0), Running())
    assert len(_session_titles(infos, ViewState())) == 1


def test_every_ended_session_is_counted() -> None:
    view = build_view(
        _infos(Exited(code=0), Exited(code=1)), [], [], [], ViewState(), now=NOW, home=None
    )
    assert InfoLine("2 ended (e to show)") in view.lines
