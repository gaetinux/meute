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


_ALLOWED_C0 = frozenset("\n\t")
INSTRUCTIONS_CONTROL = "instructions contain a control character"


def has_control_character(text: str) -> bool:
    """Tell whether `text` holds a C0 control character other than a newline or a tab.

    Instructions reach Claude on its command line, where a NUL cannot go.
    """
    return any(char < " " and char not in _ALLOWED_C0 for char in text)


def one_line(text: str, limit: int, *, ellipsis: bool = False) -> str:
    """Return `text` on one printable line of at most `limit` characters.

    Whitespace runs collapse to one space. A longer text is cut; with `ellipsis` the cut
    keeps room for a final "…".
    """
    line = printable(" ".join(text.split()))
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "…" if ellipsis else line[:limit]


_MIN_COST = 0.10


def cost_text(cost: float | None) -> str:
    """Return `$x.xx`, or "" when the cost is unknown or at most 10 cents (noise)."""
    return f"${cost:.2f}" if cost is not None and cost > _MIN_COST else ""
