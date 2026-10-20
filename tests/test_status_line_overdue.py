"""The overdue count in the tmux status line."""

from meute.core.status_line import status_text


def test_overdue_comes_last() -> None:
    assert status_text("api", 1, 42.0, overdue=2) == "▶ api · 1 need attention · 5h 42% · 2 overdue"
    assert status_text(None, 0, None, overdue=2) == "2 overdue"


def test_no_overdue_changes_nothing() -> None:
    assert status_text("api", 1, 42.0, overdue=0) == status_text("api", 1, 42.0)
