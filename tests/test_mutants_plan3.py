"""Tests added after mutmut: plan 3 behaviour that earlier tests left unchecked."""

import json
import sqlite3
import stat
import time
import zoneinfo
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from meute.claude.agents import kill_agents, run_agents, start_agents
from meute.claude.settings import settings_document, write_settings
from meute.core import clock
from meute.core.config import config_get
from meute.core.config_validate import QuotasConfig, validate_config
from meute.core.db.claude_sessions import get_claude_details, session_events
from meute.core.db.connection import Database
from meute.core.db.hook_apply import apply_hook
from meute.core.db.samples import latest_metrics, record_metrics
from meute.core.db.sessions import create_session
from meute.core.errors import InvalidInput, NotFound
from meute.core.hooks import HookEffect, interpret_hook
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Idle
from meute.core.statusline import StatuslineData
from meute.core.statusline_render import render_statusline
from support import FIXED

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")
NEW_YORK = ZoneInfo("America/New_York")
MONDAY_20H45_NY = datetime(2026, 10, 12, 20, 45, tzinfo=NEW_YORK)


def make(db: Database) -> None:
    create_session(
        db,
        NewSession(id=SID, agent=AgentKind.CLAUDE, title="c", cwd=Path("/w"), state=Idle()),
    )


def effect(event: str, payload: dict[str, object]) -> HookEffect:
    found = interpret_hook(event, payload)
    assert found is not None
    return found


# Hooks


def test_path_key_wins_over_an_earlier_string() -> None:
    read = effect(
        "PreToolUse", {"tool_name": "Read", "tool_input": {"description": "d", "file_path": "/a"}}
    )
    assert read.last_tool == "Read /a"


def test_tool_without_name_or_input_is_empty() -> None:
    assert effect("PreToolUse", {}).last_tool == ""


def test_session_start_history_is_the_source() -> None:
    assert effect("SessionStart", {"source": "resume"}).history == "resume"
    assert effect("SessionStart", {}).history == ""


def test_stop_keeps_newlines_and_has_no_history() -> None:
    stop = effect("Stop", {"last_assistant_message": "a\nb"})
    assert stop.last_message == "a\nb"
    assert stop.history == ""


def test_prompt_has_no_history() -> None:
    assert effect("UserPromptSubmit", {"permission_mode": "plan"}).history == ""


def test_prompt_permission_mode_is_written(db: Database) -> None:
    make(db)
    apply_hook(db, SID, "UserPromptSubmit", effect("UserPromptSubmit", {"permission_mode": "plan"}))
    assert get_claude_details(db, SID).permission_mode == "plan"


# Database


def test_metrics_round_trip_every_column(db: Database) -> None:
    make(db)
    data = StatuslineData(
        model_name="m",
        effort="high",
        context_pct=12.5,
        cost_usd=0.5,
        duration_ms=9,
        lines_added=7,
        lines_removed=3,
        worktree_name="wt",
        worktree_branch="br",
        worktree_path="/p",
        repo_host="h",
        repo_owner="o",
        repo_name="n",
    )
    assert record_metrics(db, SID, data)
    assert latest_metrics(db, SID) == data


def test_corrupt_metric_number_says_what_was_expected(db: Database) -> None:
    make(db)
    db.conn.execute(
        "INSERT INTO metric_samples (session_id, created_at, context_pct) VALUES (?, 'x', 'abc')",
        (SID,),
    )
    with pytest.raises(ValueError, match=r"^corrupt row: expected number, got 'abc'$"):
        latest_metrics(db, SID)


def test_session_events_default_to_the_latest_fifty(db: Database) -> None:
    make(db)
    for n in range(51):
        apply_hook(db, SID, f"E{n}", effect(f"E{n}", {}))
    events = session_events(db, SID)
    assert len(events) == 50
    assert events[-1].event == "E50"


def test_unknown_claude_session_names_the_session() -> None:
    with Database.in_memory() as db, pytest.raises(NotFound, match=rf"^session not found: {SID}$"):
        get_claude_details(db, SID)


def test_open_existing_missing_file_names_the_path(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with pytest.raises(FileNotFoundError) as caught:
        Database.open_existing(path, busy_timeout_ms=200)
    assert caught.value.args == (path,)


def test_open_existing_uses_the_clock_and_autocommits(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    Database.open(path, busy_timeout_ms=200).close()
    with Database.open_existing(path, busy_timeout_ms=200, clock=lambda: FIXED) as db:
        assert db.now() == FIXED
        make(db)
        db.conn.execute("UPDATE sessions SET title = 'seen' WHERE id = ?", (SID,))
        other = sqlite3.connect(path)
        try:
            assert other.execute("SELECT title FROM sessions").fetchall() == [("seen",)]
        finally:
            other.close()


# Configuration and clock


def test_stuck_after_minutes_can_be_read(tmp_path: Path) -> None:
    assert config_get(tmp_path / "config.toml", "claude.stuck_after_minutes") == "10"


def test_chain_that_is_not_a_string_is_refused() -> None:
    with pytest.raises(InvalidInput, match=r"^statusline.chain: expected a command as a string$"):
        validate_config({"statusline": {"chain": 3}})


def test_tz_with_a_leading_colon_is_the_zone() -> None:
    assert clock.local_zone({"TZ": ":Asia/Tokyo"}) == ZoneInfo("Asia/Tokyo")


def test_localtime_file_is_read_when_tz_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = next(
        Path(root) / "Asia/Tokyo"
        for root in zoneinfo.TZPATH
        if (Path(root) / "Asia/Tokyo").is_file()
    )
    copy = tmp_path / "localtime"
    copy.write_bytes(source.read_bytes())
    monkeypatch.setattr(clock, "_LOCALTIME", copy)
    assert clock.local_zone({}).utcoffset(MONDAY_20H45_NY) == timedelta(hours=9)


# Status line


def render(
    data: StatuslineData,
    now: datetime = MONDAY_20H45_NY,
    *,
    quotas: QuotasConfig | None = None,
    local: ZoneInfo = NEW_YORK,
) -> str:
    """Render at width 200, dropping the reset and grey escapes to keep assertions short."""
    text = render_statusline(
        data, user="me", now=now, quotas=quotas or QuotasConfig(), local=local, width=200
    )
    return text.replace("\033[0m", "").replace("\033[90m", "")


def test_basename_keeps_trailing_capital_x() -> None:
    assert "\033[36mBOX" in render(StatuslineData(cwd="/w/BOX"))


def test_empty_cwd_has_an_empty_basename() -> None:
    assert "\033[36m \033" not in render(StatuslineData(cwd=""))
    assert render(StatuslineData(cwd="")).startswith("\033[1;32m➜ \033[1mme \033[36m │")


def test_lines_of_one_are_shown_and_zero_is_not() -> None:
    shown = render(StatuslineData(cwd="/w", lines_added=1, lines_removed=0))
    assert shown.endswith("\033[32m+1")
    assert render(StatuslineData(cwd="/w", lines_removed=1)).endswith("\033[31m-1")


def test_lines_summing_to_zero_are_hidden() -> None:
    assert "+5" not in render(StatuslineData(cwd="/w", lines_added=5, lines_removed=-5))


def test_friday_morning_is_before_the_peak() -> None:
    friday_7h = datetime(2026, 10, 16, 7, 0, tzinfo=NEW_YORK)
    assert "(peak in ~1h)" in render(StatuslineData(cwd="/w"), friday_7h)


def test_friday_at_the_end_hour_is_the_weekend() -> None:
    friday_14h = datetime(2026, 10, 16, 14, 0, tzinfo=NEW_YORK)
    assert "(weekend)" in render(StatuslineData(cwd="/w"), friday_14h)


def test_peak_start_is_a_whole_hour_in_a_half_hour_zone() -> None:
    kolkata = render(StatuslineData(cwd="/w"), local=ZoneInfo("Asia/Kolkata"))
    assert "(until 17h)" in kolkata  # 08:00 New York = 17:30 Kolkata


def test_peak_start_of_twenty_four_is_midnight() -> None:
    quotas = QuotasConfig(peak_start_hour=24)
    assert "(until 0h)" in render(StatuslineData(cwd="/w"), quotas=quotas)


# claude agents and settings


def script(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "claude"
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_agents_runs_detached_with_its_arguments(tmp_path: Path) -> None:
    body = (
        'printf "%s|%s|%s|%s" "$*" "$(readlink /proc/$$/fd/0)" "$(readlink /proc/$$/fd/2)"'
        ' "$(($(ps -o pgid= -p $$) == $$))"'
    )
    assert run_agents(script(tmp_path, body)) == "agents --json|/dev/null|/dev/null|1"


def test_agents_output_is_decoded_leniently_and_capped(tmp_path: Path) -> None:
    assert run_agents(script(tmp_path, r"printf 'a\377'")) == "a�"
    assert run_agents(script(tmp_path, "head -c 1048577 /dev/zero")) == "\0" * (1 << 20)


def test_agents_default_timeout_is_two_seconds(tmp_path: Path) -> None:
    slow = script(tmp_path, "sleep 2.6; echo late")
    started = time.monotonic()
    assert run_agents(slow) is None
    assert time.monotonic() - started < 2.5


def test_kill_agents_reaps_the_process(tmp_path: Path) -> None:
    run = start_agents(script(tmp_path, "sleep 30"))
    assert run is not None
    kill_agents(run)
    assert run.process.returncode is not None


def test_settings_file_is_indented_json(tmp_path: Path) -> None:
    path = write_settings(tmp_path, SID, ["meute"])
    expected = json.dumps(settings_document(["meute"]), indent=2) + "\n"
    assert path.read_text(encoding="utf-8") == expected
