"""Tests for the shared builders of styled lines: rules, labelled rows, fold marks, levels."""

from meute.core.quota_view import level_role
from meute.core.styled import Role, Span, fold_mark, labelled, plain, title_rule


def test_title_rule_fills_the_width() -> None:
    rule = title_rule("plan", 12, Role.ACCENT)
    assert plain(rule) == "─ plan ─────"
    assert {span.role for span in rule} == {Role.ACCENT}


def test_title_rule_cuts_a_long_title_with_an_ellipsis() -> None:
    assert plain(title_rule("a long title", 8, Role.ACCENT)) == "─ a lon…"


def test_title_rule_without_title_is_a_plain_rule() -> None:
    assert title_rule(None, 4, Role.DIM) == (Span("────", Role.DIM),)
    assert plain(title_rule(None, -1, Role.DIM)) == ""


def test_labelled_pads_the_dim_label() -> None:
    assert labelled("Due", 6, Span("today")) == (Span("Due   ", Role.DIM), Span("today"))


def test_fold_mark() -> None:
    assert (fold_mark(folded=True), fold_mark(folded=False)) == ("▶", "▼")


def test_level_role() -> None:
    assert [level_role(pct) for pct in (10, 50, 80)] == [Role.OK, Role.WARN, Role.HIGH]
