"""Tests for the helpers the views share: the overdue count and the kept selection."""

from datetime import timedelta

from meute.core.selection import keep_selected
from meute.core.status import Done
from meute.core.views import count_overdue
from support import NOW, date_due, make_task


def test_count_overdue_counts_open_tasks_past_their_due() -> None:
    late = make_task(1, due=date_due("2026-10-13"))
    done_late = make_task(2, due=date_due("2026-10-13"), status=Done(), completed_at=NOW)
    today = make_task(3, due=date_due("2026-10-14"))
    assert count_overdue([late, done_late, today, make_task(4)], NOW) == 1
    assert count_overdue([], NOW) == 0
    assert count_overdue([late], NOW - timedelta(days=2)) == 0


def test_keep_selected_prefers_the_old_key_then_the_folded_group() -> None:
    keys = [None, "task:1", "group:b", "task:2"]
    assert keep_selected(keys, "task:2", 0, old_group="b") == 3
    assert keep_selected(keys, "task:9", 0, old_group="b") == 2
    assert keep_selected(keys, None, 1, old_group=None) == 2


def test_keep_selected_clamps_the_fallback_and_needs_a_choice() -> None:
    keys = [None, "task:1", None, "task:2"]
    assert keep_selected(keys, "task:9", 99, old_group="gone") == 3
    assert keep_selected(keys, None, -4, old_group=None) == 1
    assert keep_selected([None, None], "task:1", 0, old_group=None) == -1
