"""Tests for instant conversion and formatting."""

from datetime import UTC, datetime, timedelta

import pytest

from meute.core.errors import InvalidInput
from meute.core.instants import format_instant, from_db, parse_zoned, to_db
from support import NOW


def test_to_db_is_fixed_width_and_sorts_like_instants() -> None:
    instants = [
        datetime(2026, 10, 14, 8, 30, 0, tzinfo=UTC),
        datetime(2026, 10, 14, 8, 30, 0, 500000, tzinfo=UTC),
        datetime(2026, 10, 14, 8, 30, 1, tzinfo=UTC),
        datetime(2026, 10, 14, 8, 30, 1, 1, tzinfo=UTC),
    ]
    texts = [to_db(t) for t in instants]
    assert {len(t) for t in texts} == {27}
    assert texts == sorted(texts)


def test_to_db_round_trips_microseconds_and_rejects_naive() -> None:
    t = datetime(2026, 10, 14, 8, 30, 0, 123456, tzinfo=UTC)
    assert to_db(t) == "2026-10-14T08:30:00.123456Z"
    assert from_db(to_db(t)) == t
    assert to_db(parse_zoned("2026-10-14T10:30[Europe/Paris]")) == "2026-10-14T08:30:00.000000Z"
    with pytest.raises(ValueError, match="naive"):
        to_db(datetime(2026, 10, 14, 8, 30))  # noqa: DTZ001 — the naive value is the point


def test_format_instant_omits_zero_microseconds() -> None:
    assert format_instant(datetime(2026, 10, 15, 8, 0, tzinfo=UTC)) == "2026-10-15T08:00:00Z"
    assert (
        format_instant(datetime(2026, 10, 15, 8, 0, 0, 500000, tzinfo=UTC))
        == "2026-10-15T08:00:00.500000Z"
    )


def test_parse_zoned_reads_the_bracketed_zone() -> None:
    assert NOW.utcoffset() == timedelta(hours=2)
    assert NOW.astimezone(UTC).hour == 8
    for bad in ("2026-10-14T10:30", "2026-10-14T10:30[Mars/Olympus]", "garbage[Europe/Paris]"):
        with pytest.raises(InvalidInput):
            parse_zoned(bad)
