"""Tests for the quota bars."""

from dataclasses import replace
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from meute.core.quota_view import QuotaLine, quota_bar, quota_bar_lines
from meute.core.styled import Role, Span, plain

PARIS = ZoneInfo("Europe/Paris")


@pytest.mark.parametrize(
    ("pct", "filled"),
    [(0, 0), (4.9, 0), (5, 0), (6, 1), (62, 6), (100, 10), (130, 10), (-3, 0)],
)
def test_quota_bar_fills_round_pct_over_ten_cells(pct: float, filled: int) -> None:
    assert quota_bar(pct) == "█" * filled + "░" * (10 - filled)


def line(**changes: object) -> QuotaLine:
    return replace(
        QuotaLine(
            five_hour_pct=62.0,
            five_hour_resets_at=datetime(2026, 10, 15, 22, 10, tzinfo=UTC),
            seven_day_pct=28.0,
            seven_day_resets_at=datetime(2026, 10, 16, 1, 0, tzinfo=UTC),
            limit_at=datetime(2026, 10, 15, 19, 13, tzinfo=UTC),
            peak="✦ OFF-PEAK (weekend)",
        ),
        **changes,
    )


def test_exact_texts() -> None:
    lines = quota_bar_lines(line(), local=PARIS)
    assert [plain(item) for item in lines] == [
        "5h ██████░░░░ 62%  resets 00:10 · limit ~21:13",
        "7d ███░░░░░░░ 28%  resets Fri 03:00 · ✦ OFF-PEAK (weekend)",
    ]


def test_roles_of_the_segments() -> None:
    five, seven = quota_bar_lines(line(), local=PARIS)
    assert Span("██████░░░░ 62%", Role.WARN) in five
    assert Span(" · limit ~21:13", Role.RISKY) in five
    assert Span("███░░░░░░░ 28%", Role.OK) in seven
    assert seven[-1] == Span(" · ✦ OFF-PEAK (weekend)", Role.OK)


def test_high_level_role() -> None:
    five = quota_bar_lines(line(five_hour_pct=91.0), local=PARIS)[0]
    assert Span("█████████░ 91%", Role.HIGH) in five


def test_peak_hours_are_warn() -> None:
    seven = quota_bar_lines(line(peak="⚡ PEAK (~3h left)"), local=PARIS)[1]
    assert seven[-1].role is Role.WARN


def test_unknown_parts_are_omitted() -> None:
    lines = quota_bar_lines(
        line(five_hour_pct=None, seven_day_resets_at=None, limit_at=None), local=PARIS
    )
    assert [plain(item) for item in lines] == ["7d ███░░░░░░░ 28% · ✦ OFF-PEAK (weekend)"]


def test_limit_without_a_five_hour_line_is_dropped() -> None:
    lines = quota_bar_lines(line(five_hour_pct=None, seven_day_pct=None, peak=""), local=PARIS)
    assert lines == []


def test_peak_alone_on_its_line() -> None:
    lines = quota_bar_lines(
        line(five_hour_pct=None, seven_day_pct=None, peak="⚡ PEAK (~3h left)"), local=PARIS
    )
    assert lines == [(Span("⚡ PEAK (~3h left)", Role.WARN),)]


def test_five_hour_without_reset() -> None:
    five = quota_bar_lines(line(five_hour_resets_at=None, seven_day_pct=None), local=PARIS)[0]
    assert plain(five) == "5h ██████░░░░ 62% · limit ~21:13"
