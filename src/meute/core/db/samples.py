"""Metric and quota samples taken from the statusline, written at most every few seconds."""

from datetime import datetime, timedelta

from meute.core.db.connection import Database
from meute.core.db.rows import (
    as_instant,
    as_integer,
    as_real,
    as_text,
    fetch_all,
    fetch_one,
    optional,
)
from meute.core.instants import to_db
from meute.core.session import SessionId
from meute.core.statusline import StatuslineData

DEFAULT_MIN_INTERVAL = timedelta(seconds=30)

_METRIC_FIELDS = (
    "model",
    "effort",
    "context_pct",
    "cost_usd",
    "duration_ms",
    "lines_added",
    "lines_removed",
    "worktree_name",
    "worktree_branch",
    "worktree_path",
    "repo_host",
    "repo_owner",
    "repo_name",
)
_QUOTA_FIELDS = ("five_hour_pct", "five_hour_resets_at", "seven_day_pct", "seven_day_resets_at")
_METRIC_COLUMNS = ", ".join(_METRIC_FIELDS)
_QUOTA_COLUMNS = ", ".join(_QUOTA_FIELDS)
_METRIC_MARKS = ", ".join("?" * len(_METRIC_FIELDS))
_QUOTA_MARKS = ", ".join("?" * len(_QUOTA_FIELDS))

type _Values = tuple[str | float | int | None, ...]


def _metric_values(data: StatuslineData) -> _Values:
    return (
        data.model_name,
        data.effort,
        data.context_pct,
        data.cost_usd,
        data.duration_ms,
        data.lines_added,
        data.lines_removed,
        data.worktree_name,
        data.worktree_branch,
        data.worktree_path,
        data.repo_host,
        data.repo_owner,
        data.repo_name,
    )


def _quota_values(data: StatuslineData) -> _Values:
    return (
        data.five_hour_pct,
        None if data.five_hour_resets_at is None else to_db(data.five_hour_resets_at),
        data.seven_day_pct,
        None if data.seven_day_resets_at is None else to_db(data.seven_day_resets_at),
    )


def _should_write(
    last: tuple[object, ...] | None, values: _Values, now: datetime, min_interval: timedelta
) -> bool:
    """Tell whether `values` differ from the latest sample `last`, or `last` is old enough."""
    if last is None:
        return True
    return tuple(last[1:]) != values or now - as_instant(last[0]) >= min_interval


def record_metrics(
    db: Database,
    session_id: SessionId,
    data: StatuslineData,
    *,
    min_interval: timedelta = DEFAULT_MIN_INTERVAL,
) -> bool:
    """Record the metrics of `data` for a session; return whether a row was written.

    Nothing is written when the session does not exist, or when no stored value differs
    from the session's latest sample and that sample is younger than `min_interval`.
    """
    values = _metric_values(data)
    now = db.now()
    # Read before taking the write lock: a race may add one extra sample, which is harmless.
    if fetch_one(db.conn, "SELECT 1 FROM sessions WHERE id = ?", (session_id,)) is None:
        return False
    last = fetch_one(
        db.conn,
        f"SELECT created_at, {_METRIC_COLUMNS} FROM metric_samples"  # noqa: S608 — fixed column names
        " WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    )
    if not _should_write(last, values, now, min_interval):
        return False
    with db.transaction() as conn:
        conn.execute(
            f"INSERT INTO metric_samples (session_id, created_at, {_METRIC_COLUMNS})"  # noqa: S608 — fixed column names
            f" VALUES (?, ?, {_METRIC_MARKS})",
            (session_id, to_db(now), *values),
        )
    return True


def record_quota(
    db: Database,
    data: StatuslineData,
    *,
    min_interval: timedelta = DEFAULT_MIN_INTERVAL,
) -> bool:
    """Record the account quota of `data`; return whether a row was written.

    Nothing is written without a known percentage, or when nothing differs from the
    latest sample and that sample is younger than `min_interval`.
    """
    if data.five_hour_pct is None and data.seven_day_pct is None:
        return False
    values = _quota_values(data)
    now = db.now()
    last = fetch_one(
        db.conn,
        f"SELECT created_at, {_QUOTA_COLUMNS} FROM quota_samples"  # noqa: S608 — fixed column names
        " ORDER BY id DESC LIMIT 1",
    )
    if not _should_write(last, values, now, min_interval):
        return False
    with db.transaction() as conn:
        conn.execute(
            f"INSERT INTO quota_samples (created_at, {_QUOTA_COLUMNS})"  # noqa: S608 — fixed column names
            f" VALUES (?, {_QUOTA_MARKS})",
            (to_db(now), *values),
        )
    return True


def latest_metrics(db: Database, session_id: SessionId) -> StatuslineData | None:
    """Return the latest metric sample of a session, or None."""
    row = fetch_one(
        db.conn,
        f"SELECT {_METRIC_COLUMNS} FROM metric_samples WHERE session_id = ?"  # noqa: S608 — fixed column names
        " ORDER BY id DESC LIMIT 1",
        (session_id,),
    )
    if row is None:
        return None
    return StatuslineData(
        model_name=optional(as_text, row[0]),
        effort=optional(as_text, row[1]),
        context_pct=optional(as_real, row[2]),
        cost_usd=optional(as_real, row[3]),
        duration_ms=optional(as_integer, row[4]),
        lines_added=optional(as_integer, row[5]),
        lines_removed=optional(as_integer, row[6]),
        worktree_name=optional(as_text, row[7]),
        worktree_branch=optional(as_text, row[8]),
        worktree_path=optional(as_text, row[9]),
        repo_host=optional(as_text, row[10]),
        repo_owner=optional(as_text, row[11]),
        repo_name=optional(as_text, row[12]),
    )


def latest_quota(db: Database) -> StatuslineData | None:
    """Return the latest quota sample (any session) as quota fields only, or None."""
    row = fetch_one(
        db.conn,
        f"SELECT {_QUOTA_COLUMNS} FROM quota_samples ORDER BY id DESC LIMIT 1",  # noqa: S608 — fixed column names
    )
    if row is None:
        return None
    return StatuslineData(
        five_hour_pct=optional(as_real, row[0]),
        five_hour_resets_at=optional(as_instant, row[1]),
        seven_day_pct=optional(as_real, row[2]),
        seven_day_resets_at=optional(as_instant, row[3]),
    )


def quota_history(db: Database, *, since: datetime) -> list[tuple[datetime, float]]:
    """Return `(created_at, five_hour_pct)` of the quota samples from `since`, oldest first.

    Samples without a known five-hour percentage are left out.
    """
    rows = fetch_all(
        db.conn,
        "SELECT created_at, five_hour_pct FROM quota_samples"
        " WHERE created_at >= ? AND five_hour_pct IS NOT NULL ORDER BY id",
        (to_db(since),),
    )
    return [(as_instant(created), as_real(pct)) for created, pct in rows]
