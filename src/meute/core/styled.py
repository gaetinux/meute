"""Styled lines: text segments tagged with a role, which the TUI maps to colours."""

from dataclasses import dataclass
from enum import Enum, auto

_ELLIPSIS = "…"


class Role(Enum):
    """What a segment of text means; the view decides how each role looks."""

    PLAIN = auto()
    TITLE = auto()
    DIM = auto()
    ACCENT = auto()
    KIND = auto()
    RUNNING = auto()
    IDLE = auto()
    ATTENTION = auto()
    RISKY = auto()
    OK = auto()
    WARN = auto()
    HIGH = auto()
    LATE = auto()
    BLOCKED = auto()
    REVIEW = auto()
    TAB_ACTIVE = auto()
    TAB = auto()


@dataclass(frozen=True, slots=True)
class Span:
    """A piece of text with the role that styles it."""

    text: str
    role: Role = Role.PLAIN


StyledLine = tuple[Span, ...]


def plain(line: StyledLine) -> str:
    """Return the text of a line without its roles."""
    return "".join(span.text for span in line)


def _cut(line: StyledLine, length: int) -> StyledLine:
    """Return the first `length` characters of `line`, keeping the roles."""
    kept: list[Span] = []
    left = length
    for span in line:
        if left <= 0:
            break
        kept.append(Span(span.text[:left], span.role))
        left -= len(span.text)
    return tuple(kept)


def _pad(line: StyledLine, width: int) -> StyledLine:
    gap = width - len(plain(line))
    return (*line, Span(" " * gap)) if gap > 0 else line


def fit(left: StyledLine, right: StyledLine, width: int) -> StyledLine:
    """Return `left` and `right` on one line of exactly `width` characters.

    `right` sticks to the right edge, with spaces between. When both do not fit, `left` is cut
    and ends with `…` to leave `right` and one space. When `right` alone cannot fit with a space,
    it is omitted and `left` is cut to `width`. A width of 0 or less gives an empty line.
    """
    if width <= 0:
        return ()
    room = width - len(plain(right)) - 1
    if not right or room < 1:
        return _pad(_cut(left, width), width)
    if len(plain(left)) <= room:
        return (*_pad(left, room), Span(" "), *right)
    head = _cut(left, room - 1)
    mark = Span(_ELLIPSIS, head[-1].role if head else Role.PLAIN)
    return (*head, mark, Span(" "), *right)


def clip(line: StyledLine, width: int) -> StyledLine:
    """Return `line` as is when it fits `width`, else cut to `width` and ending with `…`."""
    if width <= 0:
        return ()
    return line if len(plain(line)) <= width else (*fit(line, (), width - 1), Span(_ELLIPSIS))


_RULE = "─"


def title_rule(title: str | None, width: int, role: Role) -> StyledLine:
    """Return a rule `width` columns wide: `─ {title} ───…`, or only `─` without a title.

    A title too long for `width` is cut and ends with `…`. `title` must already be printable.
    """
    if title is None:
        return (Span(_RULE * max(width, 0), role),)
    head = f"{_RULE} {title} "
    return clip((Span(head + _RULE * max(width - len(head), 0), role),), width)


def labelled(label: str, width: int, *value: Span) -> StyledLine:
    """Return `label` in the dim role, padded to `width` columns, then the `value` segments."""
    return (Span(label.ljust(width), Role.DIM), *value)


def fold_mark(*, folded: bool) -> str:
    """Return the mark of a foldable heading: `▶` when folded, `▼` when open."""
    return "▶" if folded else "▼"
