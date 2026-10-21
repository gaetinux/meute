"""Tests for styled lines: spans, roles, `plain` and `fit`."""

from hypothesis import given
from hypothesis import strategies as st

from meute.core.styled import Role, Span, fit, plain


def line(*texts: str) -> tuple[Span, ...]:
    return tuple(Span(text) for text in texts)


def test_span_defaults_to_plain_role() -> None:
    assert Span("x").role is Role.PLAIN


def test_plain_joins_the_texts() -> None:
    assert plain((Span("a", Role.DIM), Span("bc", Role.OK))) == "abc"


def test_fit_pads_between_left_and_right() -> None:
    assert plain(fit(line("left"), line("right"), 15)) == "left      right"


def test_fit_keeps_the_roles() -> None:
    fitted = fit((Span("l", Role.TITLE),), (Span("r", Role.DIM),), 5)
    assert [(s.text, s.role) for s in fitted if s.text.strip()] == [
        ("l", Role.TITLE),
        ("r", Role.DIM),
    ]


def test_fit_exact_width_with_one_space() -> None:
    assert plain(fit(line("left"), line("right"), 10)) == "left right"


def test_fit_cuts_left_with_an_ellipsis_and_keeps_a_space() -> None:
    assert plain(fit(line("a long left part"), line("right"), 12)) == "a lon… right"


def test_fit_cut_keeps_the_role_of_the_last_kept_span() -> None:
    fitted = fit((Span("abc", Role.TITLE), Span("defgh", Role.DIM)), line("r"), 8)
    assert plain(fitted) == "abcde… r"
    assert fitted[:2] == (Span("abc", Role.TITLE), Span("de", Role.DIM))
    assert fitted[2] == Span("…", Role.DIM)


def test_fit_omits_a_right_that_does_not_fit() -> None:
    assert plain(fit(line("left side"), line("too long right"), 6)) == "left s"


def test_fit_right_alone_without_room_for_a_space_is_omitted() -> None:
    assert plain(fit(line("left"), line("12345"), 5)) == "left "


def test_fit_pads_a_short_left_when_right_is_omitted() -> None:
    assert plain(fit(line("ab"), line("too long"), 4)) == "ab  "


def test_fit_width_zero_is_empty() -> None:
    assert fit(line("a"), line("b"), 0) == ()


def test_fit_empty_right_pads_left() -> None:
    assert plain(fit(line("ab"), (), 5)) == "ab   "


@given(
    left=st.text(min_size=1, max_size=40).filter(lambda t: "\n" not in t),
    right=st.text(max_size=40),
    width=st.integers(min_value=1, max_value=60),
)
def test_fit_always_fills_the_width(left: str, right: str, width: int) -> None:
    assert len(plain(fit(line(left), line(right), width))) == width
