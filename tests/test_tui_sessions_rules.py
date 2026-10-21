"""The rule under the quota bars of the Sessions tab and the band colour, as in mockup C2."""

from textual.pilot import Pilot

from meute.core.styled import Role
from meute.tui.board import BoardApp
from meute.tui.sessions_pane import BAND_STYLE, ROLE_STYLES
from test_tui_sessions import (
    _content,  # pyright: ignore[reportPrivateUsage] — Sessions tab test helper
    _rich_data,  # pyright: ignore[reportPrivateUsage] — Sessions tab test helper
    _scenario,  # pyright: ignore[reportPrivateUsage] — Sessions tab test helper
)


def test_a_dim_rule_closes_the_quota_lines_as_wide_as_the_tasks_one() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        quota = _content(app, "quota")
        *bars, rule = quota.plain.splitlines()
        assert len(bars) == 2
        start = quota.plain.index(rule)
        assert {str(s.style) for s in quota.spans if s.start >= start} == {ROLE_STYLES[Role.DIM]}
        await pilot.press("tab")
        tasks_rule = _content(app, "quota").plain.splitlines()[-1]
        assert set(rule) == {"─"}
        assert rule == tasks_rule

    _ = _scenario(_rich_data(), steps)


def test_the_band_shows_on_a_dark_terminal() -> None:
    assert BAND_STYLE == "on #4a1c22"
