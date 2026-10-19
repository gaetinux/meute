"""Tests for recording metric and quota samples with write throttling."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from meute.core.db.connection import Database
from meute.core.db.rows import as_integer, fetch_one
from meute.core.db.samples import (
    latest_metrics,
    latest_metrics_by_session,
    latest_quota,
    record_metrics,
    record_quota,
)
from meute.core.db.sessions import create_session
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from meute.core.statusline import StatuslineData, parse_statusline
from support import FIXED, claude_statusline_fixture

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")
T0 = FIXED


class Clock:
    """A settable clock."""

    def __init__(self) -> None:
        self.at = T0

    def __call__(self) -> datetime:
        return self.at

    def after(self, seconds: float) -> None:
        self.at = T0 + timedelta(seconds=seconds)


def clocked(db: Database) -> tuple[Database, Clock]:
    clock = Clock()
    return replace(db, clock=clock), clock


def make(db: Database) -> None:
    create_session(
        db,
        NewSession(id=SID, agent=AgentKind.CLAUDE, title="c", cwd=Path("/work"), state=Running()),
    )


def count(db: Database, table: str) -> int:
    row = fetch_one(db.conn, f"SELECT COUNT(*) FROM {table}")  # noqa: S608 — fixed table names
    assert row is not None
    return as_integer(row[0])


DATA = parse_statusline(claude_statusline_fixture("statusline-2"))


def test_metrics_round_trip() -> None:
    with Database.in_memory(clock=lambda: T0) as db:
        make(db)
        assert latest_metrics(db, SID) is None
        assert record_metrics(db, SID, DATA) is True
        loaded = latest_metrics(db, SID)
        assert loaded is not None
        assert loaded.model_name == "Opus 5.5"
        assert loaded.effort == "medium"
        assert loaded.context_pct == 4
        assert loaded.cost_usd == 0.1125694
        assert loaded.duration_ms == 3830
        assert (loaded.repo_host, loaded.repo_owner, loaded.repo_name) == (
            "github.com",
            "user",
            "meute",
        )
        assert loaded.five_hour_pct is None


def test_same_metrics_inside_the_interval_write_once() -> None:
    with Database.in_memory() as raw:
        db, clock = clocked(raw)
        make(db)
        assert record_metrics(db, SID, DATA) is True
        clock.after(10)
        assert record_metrics(db, SID, DATA) is False
        assert count(db, "metric_samples") == 1


def test_same_metrics_after_the_interval_write_again() -> None:
    with Database.in_memory() as raw:
        db, clock = clocked(raw)
        make(db)
        record_metrics(db, SID, DATA)
        clock.after(29.9)
        assert record_metrics(db, SID, DATA) is False
        clock.after(30)
        assert record_metrics(db, SID, DATA) is True
        assert count(db, "metric_samples") == 2


def test_changed_metrics_write_at_once() -> None:
    with Database.in_memory() as raw:
        db, clock = clocked(raw)
        make(db)
        record_metrics(db, SID, DATA)
        clock.after(5)
        assert record_metrics(db, SID, replace(DATA, context_pct=5)) is True
        assert count(db, "metric_samples") == 2
        loaded = latest_metrics(db, SID)
        assert loaded is not None
        assert loaded.context_pct == 5


def test_every_stored_field_triggers_a_write() -> None:
    changes = [
        {"model_name": "m"},
        {"effort": "high"},
        {"context_pct": 9.0},
        {"cost_usd": 1.0},
        {"duration_ms": 1},
        {"lines_added": 1},
        {"lines_removed": 1},
        {"worktree_name": "w"},
        {"worktree_branch": "b"},
        {"worktree_path": "/p"},
        {"repo_host": "h"},
        {"repo_owner": "o"},
        {"repo_name": "n"},
    ]
    for change in changes:
        with Database.in_memory() as raw:
            db, clock = clocked(raw)
            make(db)
            record_metrics(db, SID, DATA)
            clock.after(1)
            assert record_metrics(db, SID, replace(DATA, **change)) is True, change


def test_unstored_fields_do_not_trigger_a_write() -> None:
    with Database.in_memory() as raw:
        db, clock = clocked(raw)
        make(db)
        record_metrics(db, SID, DATA)
        clock.after(1)
        assert record_metrics(db, SID, replace(DATA, cwd="/elsewhere", agent_name="a")) is False


def test_throttling_compares_with_the_latest_sample() -> None:
    with Database.in_memory() as raw:
        db, clock = clocked(raw)
        make(db)
        record_metrics(db, SID, DATA)
        clock.after(5)
        record_metrics(db, SID, replace(DATA, context_pct=5))
        clock.after(6)
        assert record_metrics(db, SID, replace(DATA, context_pct=5)) is False


def test_unknown_session_records_nothing() -> None:
    with Database.in_memory(clock=lambda: T0) as db:
        assert record_metrics(db, SID, DATA) is False
        assert count(db, "metric_samples") == 0


def test_custom_min_interval() -> None:
    with Database.in_memory() as raw:
        db, clock = clocked(raw)
        make(db)
        record_metrics(db, SID, DATA, min_interval=timedelta(seconds=5))
        clock.after(5)
        assert record_metrics(db, SID, DATA, min_interval=timedelta(seconds=5)) is True


def test_quota_round_trip_and_throttling() -> None:
    with Database.in_memory() as raw:
        db, clock = clocked(raw)
        assert latest_quota(db) is None
        assert record_quota(db, DATA) is True
        clock.after(10)
        assert record_quota(db, DATA) is False
        clock.after(30)
        assert record_quota(db, DATA) is True
        assert count(db, "quota_samples") == 2
        loaded = latest_quota(db)
        assert loaded == StatuslineData(
            five_hour_pct=27,
            five_hour_resets_at=datetime(2026, 10, 18, 16, 20, tzinfo=UTC),
            seven_day_pct=42,
            seven_day_resets_at=datetime.fromtimestamp(1792717200, UTC),
        )


def test_quota_change_writes_at_once() -> None:
    with Database.in_memory() as raw:
        db, clock = clocked(raw)
        record_quota(db, DATA)
        clock.after(1)
        assert record_quota(db, replace(DATA, five_hour_pct=28)) is True
        clock.after(2)
        assert record_quota(db, replace(DATA, five_hour_resets_at=T0.replace(year=2030))) is True
        clock.after(3)
        assert record_quota(db, replace(DATA, seven_day_pct=43)) is True
        clock.after(4)
        assert record_quota(db, replace(DATA, seven_day_resets_at=None)) is True


def test_quota_without_percentage_records_nothing() -> None:
    with Database.in_memory(clock=lambda: T0) as db:
        assert record_quota(db, StatuslineData()) is False
        first = parse_statusline(claude_statusline_fixture("statusline-1"))
        assert record_quota(db, first) is False
        assert count(db, "quota_samples") == 0


def test_quota_with_one_percentage_is_recorded() -> None:
    with Database.in_memory(clock=lambda: T0) as db:
        assert record_quota(db, StatuslineData(seven_day_pct=3)) is True
        loaded = latest_quota(db)
        assert loaded is not None
        assert loaded.seven_day_pct == 3
        assert loaded.five_hour_pct is None


def test_latest_quota_is_the_most_recent() -> None:
    with Database.in_memory() as raw:
        db, clock = clocked(raw)
        record_quota(db, StatuslineData(five_hour_pct=1))
        clock.after(1)
        record_quota(db, StatuslineData(five_hour_pct=2))
        loaded = latest_quota(db)
        assert loaded is not None
        assert loaded.five_hour_pct == 2


def test_huge_cost_is_recorded_without_error() -> None:
    with Database.in_memory(clock=lambda: T0) as db:
        make(db)
        data = parse_statusline({"cost": {"total_cost_usd": 10**30, "total_duration_ms": 10**30}})
        assert record_metrics(db, SID, data) is True


def test_quota_history_lists_known_five_hour_samples_since_a_date() -> None:
    from meute.core.db.samples import quota_history  # noqa: PLC0415 — new tests only

    clock = Clock()
    with Database.in_memory(clock=clock) as db:
        db = replace(db, clock=clock)  # noqa: PLW2901 — same database, settable clock
        for seconds, five, seven in (
            (0, 10.0, 1.0),
            (60, None, 2.0),
            (120, 20.0, 2.0),
            (180, 30.0, 3.0),
        ):
            clock.after(seconds)
            data = StatuslineData(five_hour_pct=five, seven_day_pct=seven)
            assert record_quota(db, data) is True
        history = quota_history(db, since=T0 + timedelta(seconds=100))
    assert history == [(T0 + timedelta(seconds=120), 20.0), (T0 + timedelta(seconds=180), 30.0)]


OTHER = SessionId("bbbb2222-0000-4000-8000-000000000000")
NONE_YET = SessionId("cccc3333-0000-4000-8000-000000000000")


def test_latest_metrics_by_session_matches_one_query_per_session() -> None:
    with Database.in_memory(clock=lambda: T0) as db:
        make(db)
        create_session(
            db,
            NewSession(
                id=OTHER, agent=AgentKind.CLAUDE, title="o", cwd=Path("/work"), state=Running()
            ),
        )
        record_metrics(db, SID, DATA)
        record_metrics(db, SID, replace(DATA, context_pct=5))
        record_metrics(db, OTHER, replace(DATA, context_pct=9))
        ids = [SID, OTHER, NONE_YET]
        found = latest_metrics_by_session(db, ids)
        assert set(found) == {SID, OTHER}
        assert found[SID] == latest_metrics(db, SID)
        assert found[OTHER] == latest_metrics(db, OTHER)
        assert found[SID].context_pct == 5
        assert latest_metrics_by_session(db, []) == {}
        assert latest_metrics_by_session(db, [OTHER]).keys() == {OTHER}
