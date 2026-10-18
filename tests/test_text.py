"""`printable` neutralises control and bidi characters."""

import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st

from meute.core.text import printable


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a\x1b[31mb", "a\ufffd[31mb"),
        ("x\u202ey", "x\ufffdy"),
        ("x\u2066y\u2069", "x\ufffdy\ufffd"),
        ("a\tb", "a b"),
        ("l1\nl2", "l1\ufffdl2"),
        ("\x85", "\ufffd"),
        ("\x7f\x00\x07", "\ufffd\ufffd\ufffd"),
        ("café 日本 🐺", "café 日本 🐺"),
    ],
)
def test_printable(text: str, expected: str) -> None:
    assert printable(text) == expected


def test_keep_newlines() -> None:
    assert printable("l1\nl2\x1b", keep_newlines=True) == "l1\nl2\ufffd"
    assert printable("a\tb", keep_newlines=True) == "a b"


@given(text=st.text(), keep=st.booleans())
def test_no_control_character_survives(text: str, *, keep: bool) -> None:
    result = printable(text, keep_newlines=keep)
    allowed = "\n" if keep else ""
    assert all(unicodedata.category(c) != "Cc" or c in allowed for c in result)
    assert not any("\u202a" <= c <= "\u202e" or "\u2066" <= c <= "\u2069" for c in result)
