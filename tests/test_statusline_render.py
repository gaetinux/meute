"""The status line: a port of the author's `statusline-command.sh`."""

import re
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

import pytest
from syrupy.assertion import SnapshotAssertion

from meute.core.config_validate import QuotasConfig
from meute.core.statusline import StatuslineData
from meute.core.statusline_render import render_statusline, statusline_width

PARIS = ZoneInfo("Europe/Paris")
NEW_YORK = ZoneInfo("America/New_York")
SEP = " \033[90m│\033[0m "
ESCAPE = re.compile(r"\033\[[0-9;]*m")
HEADER = "\033[1;32m➜\033[0m \033[1mme\033[0m \033[36mmeute\033[0m"
WEDNESDAY_10H_NY = datetime(2026, 10, 14, 10, 0, tzinfo=NEW_YORK)

RICH = StatuslineData(
    cwd="/home/me/git/meute",
    model_name="Opus 5.5",
    five_hour_pct=42,
    context_pct=63,
    seven_day_pct=71,
    cost_usd=1.2345,
    duration_ms=3_900_000,
    lines_added=120,
    lines_removed=30,
    worktree_name="feat-x",
    agent_name="reviewer",
)


def render(
    data: StatuslineData | None = None,
    *,
    now: datetime = WEDNESDAY_10H_NY,
    local: tzinfo = PARIS,
    width: int = 200,
    quotas: QuotasConfig | None = None,
) -> str:
    return render_statusline(
        StatuslineData(cwd="/home/me/git/meute") if data is None else data,
        user="me",
        now=now,
        quotas=QuotasConfig() if quotas is None else quotas,
        local=local,
        width=width,
    )


def segments(text: str) -> list[str]:
    return text.split(SEP)


def visible(text: str) -> str:
    return ESCAPE.sub("", text)


def show(text: str) -> str:
    return text.replace("\033", "\\033")


PEAK_10H = "\033[1;31m⚡ PEAK\033[0m \033[90m(~4h left)\033[0m"


def test_minimal_line_is_header_model_and_peak() -> None:
    assert render() == SEP.join([HEADER, "\033[35mClaude\033[0m", PEAK_10H])


def test_directory_is_the_basename_or_a_tilde() -> None:
    assert "\033[36mproj\033[0m" in render(StatuslineData(cwd="/a/proj/"))
    assert "\033[36m~\033[0m" in render(StatuslineData())
    assert "\033[36m/\033[0m" in render(StatuslineData(cwd="/"))


@pytest.mark.parametrize(
    ("pct", "bar"),
    [(0, "░░░░░"), (9, "░░░░░"), (10, "█░░░░"), (89, "████░"), (90, "█████"),
     (100, "█████"), (150, "█████"), (-30, "░░░░░")],
)  # fmt: skip
def test_bar_fills_from_the_percentage(pct: float, bar: str) -> None:
    line = render(StatuslineData(five_hour_pct=pct))
    assert f"{bar}\033[0m \033[90m5h\033[0m" in line


@pytest.mark.parametrize(
    ("pct", "color"), [(0, "32"), (49, "32"), (50, "33"), (79, "33"), (80, "31"), (100, "31")]
)
def test_color_follows_the_percentage(pct: float, color: str) -> None:
    assert f"\033[{color}m" in segments(render(StatuslineData(five_hour_pct=pct)))[2]


@pytest.mark.parametrize(("raw", "shown"), [(0.5, 0), (1.5, 2), (2.5, 2), (49.4, 49), (49.6, 50)])
def test_percentages_round_half_to_even_like_printf(raw: float, shown: int) -> None:
    assert segments(render(StatuslineData(five_hour_pct=raw)))[2].endswith(f" {shown}%")


def test_five_hour_segment() -> None:
    line = render(StatuslineData(five_hour_pct=42))
    assert segments(line)[2] == "\033[32m██░░░\033[0m \033[90m5h\033[0m 42%"


def test_context_segment() -> None:
    parts = segments(render(StatuslineData(context_pct=63)))
    assert parts[3] == "\033[33m███░░\033[0m \033[90mctx\033[0m 63%"


@pytest.mark.parametrize(("cost", "shown"), [(0.10, None), (0.11, "$0.11"), (1.2345, "$1.23")])
def test_cost_only_above_ten_cents(cost: float, shown: str | None) -> None:
    parts = segments(render(StatuslineData(cost_usd=cost)))
    assert parts[3:] == ([] if shown is None else [shown])


def test_worktree_and_agent_segments() -> None:
    parts = segments(render(StatuslineData(worktree_name="wt", agent_name="ag")))
    assert parts[3:] == ["\033[36mwt\033[0m", "\033[36mag\033[0m"]


def test_empty_names_are_absent() -> None:
    assert len(segments(render(StatuslineData(worktree_name="", agent_name="")))) == 3


def test_seven_day_only_above_fifty() -> None:
    assert segments(render(StatuslineData(seven_day_pct=50)))[3:] == []
    parts = segments(render(StatuslineData(seven_day_pct=51)))
    assert parts[3:] == ["\033[33m███░░\033[0m \033[90m7d\033[0m 51%"]


@pytest.mark.parametrize(
    ("ms", "shown"),
    [(600_000, None), (600_001, "10m"), (3_599_999, "59m"), (3_900_000, "1h05m"),
     (36_000_000, "10h00m")],
)  # fmt: skip
def test_duration_only_beyond_ten_minutes(ms: int, shown: str | None) -> None:
    parts = segments(render(StatuslineData(duration_ms=ms)))
    assert parts[3:] == ([] if shown is None else [f"\033[90m{shown}\033[0m"])


@pytest.mark.parametrize(
    ("added", "removed", "shown"),
    [(3, None, "\033[32m+3\033[0m"), (None, 2, "\033[31m-2\033[0m"),
     (3, 2, "\033[32m+3\033[0m \033[31m-2\033[0m"), (0, 0, None), (None, None, None),
     (0, 2, "\033[31m-2\033[0m")],
)  # fmt: skip
def test_lines_segment(added: int | None, removed: int | None, shown: str | None) -> None:
    parts = segments(render(StatuslineData(lines_added=added, lines_removed=removed)))
    assert parts[3:] == ([] if shown is None else [shown])


def test_segments_come_in_the_scripts_order() -> None:
    parts = segments(render(RICH))
    assert [visible(part) for part in parts[2:]] == [
        "██░░░ 5h 42%",
        "⚡ PEAK (~4h left)",
        "███░░ ctx 63%",
        "$1.23",
        "feat-x",
        "reviewer",
        "████░ 7d 71%",
        "1h05m",
        "+120 -30",
    ]


def at(zoned: datetime) -> str:
    return segments(render(now=zoned))[2]


def test_peak_during_weekday_hours() -> None:
    assert at(datetime(2026, 10, 13, 10, 0, tzinfo=NEW_YORK)) == PEAK_10H
    assert "(~6h left)" in at(datetime(2026, 10, 13, 8, 0, tzinfo=NEW_YORK))
    assert "(~1h left)" in at(datetime(2026, 10, 13, 13, 59, tzinfo=NEW_YORK))


def test_off_peak_after_the_end_names_the_local_start() -> None:
    expected = "\033[1;32m✦ OFF-PEAK\033[0m \033[90m(until 14h)\033[0m"
    assert at(datetime(2026, 10, 13, 15, 0, tzinfo=NEW_YORK)) == expected
    assert at(datetime(2026, 10, 13, 14, 0, tzinfo=NEW_YORK)) == expected


def test_off_peak_before_the_start() -> None:
    expected = "\033[1;32m✦ OFF-PEAK\033[0m \033[90m(peak in ~2h)\033[0m"
    assert at(datetime(2026, 10, 13, 6, 0, tzinfo=NEW_YORK)) == expected


def test_weekend_and_friday_evening_are_off_peak() -> None:
    expected = "\033[1;32m✦ OFF-PEAK\033[0m \033[90m(weekend)\033[0m"
    assert at(datetime(2026, 10, 16, 15, 0, tzinfo=NEW_YORK)) == expected  # Friday
    assert at(datetime(2026, 10, 17, 10, 0, tzinfo=NEW_YORK)) == expected  # Saturday
    assert at(datetime(2026, 10, 18, 10, 0, tzinfo=NEW_YORK)) == expected  # Sunday
    assert "PEAK\033[0m \033[90m(~4h" in at(datetime(2026, 10, 16, 10, 0, tzinfo=NEW_YORK))


def test_peak_is_judged_in_the_peak_zone_whatever_the_instant_zone() -> None:
    assert at(datetime(2026, 10, 13, 16, 0, tzinfo=PARIS)) == PEAK_10H


def test_peak_hours_come_from_the_quotas_section() -> None:
    quotas = QuotasConfig(peak_timezone="Europe/Paris", peak_start_hour=9, peak_end_hour=18)
    noon = datetime(2026, 10, 13, 12, 0, tzinfo=PARIS)
    line = segments(render(now=noon, quotas=quotas, local=NEW_YORK))[2]
    assert "(~6h left)" in line
    evening = datetime(2026, 10, 13, 19, 0, tzinfo=PARIS)
    assert "(until 3h)" in segments(render(now=evening, quotas=quotas, local=NEW_YORK))[2]


def test_wide_terminal_keeps_every_segment() -> None:
    assert len(segments(render(RICH, width=200))) == 11


def test_tiny_terminal_keeps_only_the_always_segments() -> None:
    assert [visible(part) for part in segments(render(RICH, width=1))] == [
        "➜ me meute",
        "Opus 5.5",
        "██░░░ 5h 42%",
        "⚡ PEAK (~4h left)",
    ]


def test_tier_three_is_dropped_first_and_re_added_while_it_fits() -> None:
    full = render(RICH)
    base = SEP.join(segments(full)[:-3])  # without 7d, duration and lines
    width = len(visible(base))
    line = render(RICH, width=width)
    assert line == base
    # room for the 7d segment only
    seven = segments(full)[-3]
    room = len(visible(base + SEP + seven))
    assert render(RICH, width=room) == base + SEP + seven
    # the duration does not fit after skipping nothing: re-adding is greedy in order
    duration = segments(full)[-2]
    assert render(RICH, width=room + len(visible(SEP + duration))) == (
        base + SEP + seven + SEP + duration
    )


def test_a_later_tier_three_segment_can_fit_after_an_earlier_one_did_not() -> None:
    data = StatuslineData(
        cwd="/home/me/git/meute", seven_day_pct=71, duration_ms=3_900_000, lines_added=1
    )
    full = render(data)
    parts = segments(full)
    base = SEP.join(parts[:3])
    width = len(visible(base + SEP + parts[-1]))  # lines fit, 7d and duration do not
    assert render(data, width=width) == base + SEP + parts[-1]


def test_second_fold_re_adds_in_worktree_agent_context_cost_order() -> None:
    parts = segments(render(RICH))
    base = SEP.join(parts[:2] + parts[2:4])  # header, model, 5h, peak
    wt, ag, ctx = parts[6], parts[7], parts[4]
    width = len(visible(base + SEP + wt + SEP + ag))
    assert render(RICH, width=width) == base + SEP + wt + SEP + ag
    width = len(visible(base + SEP + wt + SEP + ag + SEP + ctx))
    assert render(RICH, width=width) == base + SEP + wt + SEP + ag + SEP + ctx


def test_first_fold_keeps_tier_two_in_script_order() -> None:
    parts = segments(render(RICH))
    base = SEP.join(parts[:8])  # up to the agent
    width = len(visible(base))
    assert render(RICH, width=width) == base


def test_length_is_the_visible_length() -> None:
    line = render(RICH, width=10_000)
    assert len(visible(line)) < len(line)
    assert render(RICH, width=len(visible(line))) == line
    assert render(RICH, width=len(visible(line)) - 1) != line


@pytest.mark.parametrize("width", [200, 120, 80, 60])
def test_snapshot_of_a_rich_line(width: int, snapshot: SnapshotAssertion) -> None:
    assert show(render(RICH, width=width)) == snapshot


def test_claude_data_cannot_inject_escapes() -> None:
    hostile = "\x1b]0;x\x07"
    data = StatuslineData(
        cwd=f"/a/{hostile}", model_name=hostile, worktree_name=hostile, agent_name=hostile
    )
    line = render_statusline(
        data,
        user=hostile,
        now=WEDNESDAY_10H_NY,
        quotas=QuotasConfig(),
        local=PARIS,
        width=200,
    )
    assert "\x1b" not in ESCAPE.sub("", line)
    assert "\x07" not in line


def test_width_prefers_columns_then_the_terminal_then_200() -> None:
    assert statusline_width({"COLUMNS": "120"}, lambda: None) == 120
    assert statusline_width({"COLUMNS": "120"}, lambda: 300) == 120
    assert statusline_width({}, lambda: 150) == 150
    assert statusline_width({}, lambda: None) == 200
    assert statusline_width({"COLUMNS": "nope"}, lambda: None) == 200
    assert statusline_width({"COLUMNS": "0"}, lambda: None) == 200


def test_width_of_eighty_or_less_asks_the_terminal_like_the_script() -> None:
    assert statusline_width({"COLUMNS": "80"}, lambda: None) == 200
    assert statusline_width({"COLUMNS": "80"}, lambda: 60) == 60
    assert statusline_width({"COLUMNS": "60"}, lambda: 0) == 200
