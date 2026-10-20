"""Tests for the tabs line and the totals."""

from meute.core.board_header import Tab, sessions_totals, tabs_line, tasks_totals
from meute.core.styled import Role, Span, plain


def test_sessions_active_without_overdue() -> None:
    result = tabs_line(Tab.SESSIONS, overdue=0, totals="4 live", width=72)
    assert plain(result) == " Sessions  Tasks " + " " * (72 - 17 - 6) + "4 live"
    assert result[0] == Span(" Sessions ", Role.TAB_ACTIVE)
    assert result[1] == Span(" Tasks ", Role.TAB)


def test_tasks_active_with_overdue() -> None:
    result = tabs_line(Tab.TASKS, overdue=2, totals="12 open · 2 overdue", width=72)
    text = plain(result)
    assert text.startswith(" Sessions  Tasks  2!")
    assert text.endswith("12 open · 2 overdue")
    assert len(text) == 72
    assert result[0] == Span(" Sessions ", Role.TAB)
    assert result[1] == Span(" Tasks ", Role.TAB_ACTIVE)
    assert result[2] == Span(" 2!", Role.HIGH)
    assert result[-1] == Span("12 open · 2 overdue", Role.DIM)


def test_sessions_totals() -> None:
    assert sessions_totals(4, 4740000, 4.4) == "4 live · 1h19 · $4.40"


def test_sessions_totals_unknown_parts() -> None:
    assert sessions_totals(0, None, None) == "0 live"
    assert sessions_totals(2, 120000, None) == "2 live · 2m"
    assert sessions_totals(2, None, 0.5) == "2 live · $0.50"


def test_tasks_totals() -> None:
    assert tasks_totals(12, 2) == "12 open · 2 overdue"
    assert tasks_totals(3, 0) == "3 open"


def test_sessions_totals_hide_a_small_cost_like_the_cards() -> None:
    assert sessions_totals(2, None, 0.1) == "2 live"
    assert sessions_totals(2, 120000, 0.0) == "2 live · 2m"
