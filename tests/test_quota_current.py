"""Quota windows whose reset has passed are no longer current (spec 7.4)."""

from datetime import UTC, datetime, timedelta

from meute.core.quota_view import current_quota
from meute.core.statusline import StatuslineData

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
SAMPLE = StatuslineData(
    five_hour_pct=97,
    five_hour_resets_at=NOW + timedelta(hours=1),
    seven_day_pct=61,
    seven_day_resets_at=NOW + timedelta(days=2),
)


def test_windows_still_running_are_kept() -> None:
    assert current_quota(SAMPLE, now=NOW) == SAMPLE


def test_a_past_five_hour_reset_drops_that_window_only() -> None:
    sample = StatuslineData(
        five_hour_pct=97,
        five_hour_resets_at=NOW - timedelta(minutes=1),
        seven_day_pct=61,
        seven_day_resets_at=SAMPLE.seven_day_resets_at,
    )
    assert current_quota(sample, now=NOW) == StatuslineData(
        seven_day_pct=61, seven_day_resets_at=SAMPLE.seven_day_resets_at
    )


def test_a_past_seven_day_reset_drops_that_window_only() -> None:
    sample = StatuslineData(
        five_hour_pct=97,
        five_hour_resets_at=SAMPLE.five_hour_resets_at,
        seven_day_pct=61,
        seven_day_resets_at=NOW - timedelta(days=1),
    )
    assert current_quota(sample, now=NOW) == StatuslineData(
        five_hour_pct=97, five_hour_resets_at=SAMPLE.five_hour_resets_at
    )


def test_a_reset_at_now_is_past() -> None:
    sample = StatuslineData(five_hour_pct=97, five_hour_resets_at=NOW)
    assert current_quota(sample, now=NOW) == StatuslineData()


def test_an_unknown_reset_keeps_the_percentage() -> None:
    sample = StatuslineData(five_hour_pct=97, seven_day_pct=61)
    assert current_quota(sample, now=NOW) == sample
