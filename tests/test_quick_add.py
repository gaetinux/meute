import contextlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from meute.core.due_parse import parse_due
from meute.core.errors import InvalidInput
from meute.core.quick_add import QuickAdd, parse_quick_add
from meute.core.status import Priority
from support import NOW, date_due


def test_full_syntax_from_spec() -> None:
    q = parse_quick_add("Review the PR @meute ! >tomorrow", NOW)
    assert q == QuickAdd(
        title="Review the PR", project="meute", priority=Priority.HIGH, due=date_due("2026-10-15")
    )


def test_invalid_due_tokens_stay_in_title() -> None:
    q = parse_quick_add("Pay >2026-02-30 >mon-25pm >+0h >soon", NOW)
    assert (q.title, q.due) == ("Pay >2026-02-30 >mon-25pm >+0h >soon", None)


def test_punctuation_and_emails_are_not_tokens() -> None:
    q = parse_quick_add("Fix the bug! write to a@b.fr", NOW)
    assert (q.title, q.project, q.priority) == (
        "Fix the bug! write to a@b.fr",
        None,
        Priority.NORMAL,
    )


def test_last_token_wins_and_triple_bang_stays() -> None:
    q = parse_quick_add("x @a @b ! !! !!!", NOW)
    assert (q.title, q.project, q.priority) == ("x !!!", "b", Priority.URGENT)


def test_lone_at_sign_stays_in_title() -> None:
    assert parse_quick_add("x @", NOW).title == "x @"


@pytest.mark.parametrize("text", ["@meute !! >tomorrow", "   ", ""])
def test_only_tokens_is_an_error(text: str) -> None:
    with pytest.raises(InvalidInput, match=r"^empty title$"):
        parse_quick_add(text, NOW)


@given(st.text(max_size=200))
def test_never_raises_anything_but_invalid_input(text: str) -> None:
    with contextlib.suppress(InvalidInput):
        parse_quick_add(text, NOW)
    parse_due(text, NOW)


@given(st.text(alphabet="abcXYZ019@!>+:- ", max_size=80))
def test_ok_title_is_non_empty_trimmed_single_spaced(text: str) -> None:
    with contextlib.suppress(InvalidInput):
        title = parse_quick_add(text, NOW).title
        assert title
        assert title == title.strip()
        assert "  " not in title


@given(st.lists(st.text(alphabet="abcdeéè", min_size=1, max_size=10), min_size=1, max_size=8))
def test_plain_words_are_kept_verbatim(words: list[str]) -> None:
    q = parse_quick_add(" ".join(words), NOW)
    assert (q.title, q.priority, q.project, q.due) == (" ".join(words), Priority.NORMAL, None, None)
