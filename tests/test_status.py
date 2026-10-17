"""Tests for the status, priority and actor enumerations."""

import pytest

from meute.core.actor import Author, Channel
from meute.core.errors import InvalidInput
from meute.core.status import (
    Blocked,
    Done,
    InProgress,
    Priority,
    Review,
    StatusKind,
    TaskStatus,
    Todo,
    is_open,
    parse_priority,
    parse_status_kind,
    status_from_kind,
    status_kind,
)

ALL = [Todo(), InProgress(), Blocked(reason="x"), Review(), Done()]


def test_kinds_labels_symbols_match_spec() -> None:
    kinds = [status_kind(s) for s in ALL]
    assert [k.value for k in kinds] == ["todo", "in_progress", "blocked", "review", "done"]
    assert "".join(k.symbol for k in kinds) == "·»✕◎✓"
    assert [k.label for k in kinds] == ["to do", "in progress", "blocked", "in review", "done"]
    assert [is_open(s) for s in ALL] == [True, True, True, True, False]


def test_parse_status_kind_round_trips_and_rejects_unknown() -> None:
    assert all(parse_status_kind(k.value) is k for k in StatusKind)
    with pytest.raises(InvalidInput, match=r"^unknown status: bloqué$"):
        parse_status_kind("bloqué")


def test_status_from_kind_trims_reason_and_requires_it_for_blocked() -> None:
    assert status_from_kind(StatusKind.BLOCKED, "  waiting for CI ") == Blocked(
        reason="waiting for CI"
    )
    assert status_from_kind(StatusKind.REVIEW, "ignored") == Review()
    for reason in (None, "", "   "):
        with pytest.raises(InvalidInput, match="needs a non-empty reason"):
            status_from_kind(StatusKind.BLOCKED, reason)


@pytest.mark.parametrize("reason", ["", "  ", " x"])
def test_blocked_rejects_blank_or_untrimmed_reason(reason: str) -> None:
    with pytest.raises(InvalidInput):
        Blocked(reason=reason)


def test_task_status_alias_works_with_isinstance() -> None:
    assert all(isinstance(s, TaskStatus) for s in ALL)
    assert not isinstance("todo", TaskStatus)


def test_priority_markers_rank_and_parsing() -> None:
    assert [p.marker for p in Priority] == ["!!", "!", "", ""]
    assert sorted(
        [Priority.LOW, Priority.URGENT, Priority.NORMAL, Priority.HIGH], key=lambda p: p.rank
    ) == [Priority.URGENT, Priority.HIGH, Priority.NORMAL, Priority.LOW]
    assert all(parse_priority(p.value) is p for p in Priority)
    with pytest.raises(InvalidInput, match=r"^unknown priority: nope$"):
        parse_priority("nope")


def test_author_and_channel_values_are_lowercase() -> None:
    assert (Author.CLAUDE.value, Channel.FORGE.value, Channel.MCP.value) == (
        "claude",
        "forge",
        "mcp",
    )
