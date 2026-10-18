"""Tests for the quota lines and the limit projection (spec 7.4)."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from meute.core.config_validate import QuotasConfig
from meute.core.quota_view import QuotaLine, projected_limit, quota_level, quota_lines
from meute.core.statusline_render import peak_text

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
PARIS = ZoneInfo("Europe/Paris")
LATER = NOW + timedelta(hours=3)


def at(minutes: float) -> datetime:
    return NOW + timedelta(minutes=minutes)


def test_steady_climb_projects_the_exact_hour() -> None:
    samples = [(at(-20), 40.0), (at(-10), 45.0), (at(0), 50.0)]
    assert projected_limit(samples, resets_at=LATER, now=NOW) == at(100)


def test_limit_after_the_reset_is_none() -> None:
    samples = [(at(-20), 40.0), (at(0), 50.0)]
    assert projected_limit(samples, resets_at=at(60), now=NOW) is None


def test_unknown_reset_still_projects() -> None:
    samples = [(at(-20), 40.0), (at(0), 50.0)]
    assert projected_limit(samples, resets_at=None, now=NOW) == at(100)


def test_single_sample_is_none() -> None:
    assert projected_limit([(at(0), 50.0)], resets_at=LATER, now=NOW) is None


def test_no_sample_is_none() -> None:
    assert projected_limit([], resets_at=LATER, now=NOW) is None


def test_two_samples_at_the_same_instant_are_none() -> None:
    assert projected_limit([(at(-5), 40.0), (at(-5), 50.0)], resets_at=LATER, now=NOW) is None


def test_flat_and_falling_slopes_are_none() -> None:
    assert projected_limit([(at(-10), 50.0), (at(0), 50.0)], resets_at=LATER, now=NOW) is None
    assert projected_limit([(at(-10), 60.0), (at(0), 50.0)], resets_at=LATER, now=NOW) is None


def test_a_drop_opens_a_new_cycle() -> None:
    samples = [(at(-25), 90.0), (at(-20), 95.0), (at(-15), 10.0), (at(-5), 15.0), (at(0), 17.5)]
    # Only the samples from the drop on: 10 -> 17.5 in 15 min, 0.5 %/min.
    assert projected_limit(samples, resets_at=None, now=NOW) == at(165)


def test_samples_older_than_thirty_minutes_are_ignored() -> None:
    samples = [(at(-60), 10.0), (at(-40), 80.0), (at(-20), 40.0), (at(0), 50.0)]
    assert projected_limit(samples, resets_at=LATER, now=NOW) == at(100)


def test_a_limit_already_reached_is_none() -> None:
    assert projected_limit([(at(-10), 98.0), (at(0), 100.0)], resets_at=None, now=NOW) is None


@given(
    st.lists(st.tuples(st.integers(-3600, 600), st.floats(0, 100)), max_size=12),
    st.one_of(st.none(), st.integers(-60, 600)),
)
def test_projection_is_none_or_between_now_and_reset(
    raw: list[tuple[int, float]], reset_minutes: int | None
) -> None:
    samples = sorted((NOW + timedelta(minutes=m / 10), pct) for m, pct in raw)
    resets_at = None if reset_minutes is None else at(reset_minutes)
    result = projected_limit(samples, resets_at=resets_at, now=NOW)
    if result is not None:
        assert result > NOW
        assert resets_at is None or result < resets_at


def line(  # noqa: PLR0913 — one keyword per field
    *,
    five_hour_pct: float | None = 42.5,
    five_hour_resets_at: datetime | None = datetime(2026, 10, 14, 13, 5, tzinfo=UTC),
    seven_day_pct: float | None = 61.4,
    seven_day_resets_at: datetime | None = datetime(2026, 10, 18, 7, 30, tzinfo=UTC),
    limit_at: datetime | None = None,
    peak: str = "PEAK",
) -> QuotaLine:
    return QuotaLine(
        five_hour_pct=five_hour_pct,
        five_hour_resets_at=five_hour_resets_at,
        seven_day_pct=seven_day_pct,
        seven_day_resets_at=seven_day_resets_at,
        limit_at=limit_at,
        peak=peak,
    )


def test_full_lines_in_local_time() -> None:
    assert quota_lines(line(), local=PARIS) == [
        "5h 42% · resets 15:05",
        "7d 61% · resets Sun 09:30",
        "PEAK",
    ]


def test_limit_text_is_appended() -> None:
    result = quota_lines(line(limit_at=datetime(2026, 10, 14, 11, 40, tzinfo=UTC)), local=PARIS)
    assert result[0] == "5h 42% · resets 15:05 · limit around 13:40 at this rate"


def test_unknown_parts_are_omitted() -> None:
    bare = line(
        five_hour_pct=None,
        five_hour_resets_at=None,
        seven_day_pct=None,
        seven_day_resets_at=None,
        peak="",
    )
    assert quota_lines(bare, local=PARIS) == []
    only_pct = line(five_hour_resets_at=None, seven_day_resets_at=None)
    assert quota_lines(only_pct, local=PARIS)[:2] == ["5h 42%", "7d 61%"]


def test_percentages_round_half_to_even() -> None:
    result = quota_lines(line(five_hour_pct=0.5, seven_day_pct=2.5), local=PARIS)
    assert result[0].startswith("5h 0% ")
    assert result[1].startswith("7d 2% ")


@pytest.mark.parametrize(
    ("pct", "level"),
    [(0, "ok"), (49.9, "ok"), (50, "warn"), (79.9, "warn"), (80, "high"), (100, "high")],
)
def test_quota_level(pct: float, level: str) -> None:
    assert quota_level(pct) == level


def test_peak_text_has_no_colour_codes() -> None:
    now = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)  # Wednesday 11:00 in New York
    assert peak_text(now, QuotasConfig(), PARIS) == "⚡ PEAK (~3h left)"
