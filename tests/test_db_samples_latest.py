"""`latest_metrics_by_session` reads each session's latest sample without scanning them all."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.samples import latest_metrics, latest_metrics_by_session, record_metrics
from meute.core.db.sessions import create_session
from meute.core.instants import to_db
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from meute.core.statusline import StatuslineData
from support import FIXED

OLD = SessionId("aaaa1111-0000-4000-8000-000000000000")
NEW = SessionId("bbbb2222-0000-4000-8000-000000000000")
_HISTORY = 5000


def _session(db: Database, session_id: SessionId) -> None:
    create_session(
        db,
        NewSession(
            id=session_id, agent=AgentKind.CLAUDE, title="s", cwd=Path("/w"), state=Running()
        ),
    )


def _bulk_samples(db: Database, session_id: SessionId, count: int) -> None:
    with db.transaction() as conn:
        conn.executemany(
            "INSERT INTO metric_samples (session_id, created_at, context_pct) VALUES (?, ?, ?)",
            (
                (session_id, to_db(FIXED + timedelta(seconds=i)), float(i % 100))
                for i in range(count)
            ),
        )


def _vm_steps(db: Database, session_ids: list[SessionId]) -> int:
    steps = 0

    def tick() -> int:
        nonlocal steps
        steps += 1
        return 0

    db.conn.set_progress_handler(tick, 1)
    try:
        _ = latest_metrics_by_session(db, session_ids)
    finally:
        db.conn.set_progress_handler(None, 1)
    return steps


# Far below `_HISTORY`: each wanted session costs a few index seeks, whatever was written.
_MAX_STEPS = 500


@pytest.mark.parametrize(
    ("writes", "wanted"),
    [
        pytest.param(((OLD, _HISTORY), (NEW, 3)), [OLD, NEW], id="long-history-first"),
        pytest.param(((NEW, 3), (OLD, _HISTORY)), [OLD, NEW], id="long-history-last"),
        pytest.param(((OLD, 1), (NEW, _HISTORY)), [OLD], id="idle-session"),
    ],
)
def test_the_cost_does_not_grow_with_the_samples_written(
    writes: tuple[tuple[SessionId, int], ...], wanted: list[SessionId]
) -> None:
    with Database.in_memory(clock=lambda: FIXED) as db:
        _session(db, OLD)
        _session(db, NEW)
        for session_id, count in writes:
            _bulk_samples(db, session_id, count)
        steps = _vm_steps(db, wanted)
    assert steps < _MAX_STEPS


def test_the_latest_sample_is_the_last_written_even_when_the_clock_went_back() -> None:
    clock_at = [FIXED + timedelta(minutes=5)]
    with Database.in_memory(clock=lambda: clock_at[0]) as db:
        _session(db, OLD)
        _session(db, NEW)
        assert record_metrics(db, OLD, StatuslineData(context_pct=1.0)) is True
        assert record_metrics(db, NEW, StatuslineData(context_pct=2.0)) is True
        clock_at[0] = FIXED  # the clock jumps back: the next samples are older on paper
        assert record_metrics(db, OLD, StatuslineData(context_pct=3.0)) is True
        assert record_metrics(db, NEW, StatuslineData(context_pct=4.0)) is True
        found = latest_metrics_by_session(db, [OLD, NEW])
        assert found == {OLD: latest_metrics(db, OLD), NEW: latest_metrics(db, NEW)}
    assert found == {
        OLD: replace(StatuslineData(), context_pct=3.0),
        NEW: replace(StatuslineData(), context_pct=4.0),
    }
