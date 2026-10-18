"""Making stored or foreign text safe to show on a terminal."""

import unicodedata

_REPLACEMENT = chr(0xFFFD)
_BIDI_CONTROLS = frozenset(chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))


def printable(text: str, *, keep_newlines: bool = False) -> str:
    """Return `text` with control and bidirectional-control characters neutralised.

    Each Unicode `Cc` character (C0, DEL, C1) and each bidi embedding, override or isolate
    control becomes U+FFFD, so no escape sequence can reach a terminal. A tab becomes a space.
    A newline is kept only when `keep_newlines` is true.
    """
    return "".join(_safe(char, keep_newlines=keep_newlines) for char in text)


def _safe(char: str, *, keep_newlines: bool) -> str:
    if char == "\n" and keep_newlines:
        return char
    if char == "\t":
        return " "
    if char in _BIDI_CONTROLS or unicodedata.category(char) == "Cc":
        return _REPLACEMENT
    return char
