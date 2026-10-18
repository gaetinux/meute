"""Parsing of the `tmux -V` output."""

import re
from dataclasses import dataclass

_VERSION = re.compile(r"tmux\s+(?:next-)?(\d+)\.(\d+)")


@dataclass(frozen=True, slots=True, kw_only=True, order=True)
class TmuxVersion:
    """A tmux `major.minor` version (letter suffixes such as `3.5a` are dropped)."""

    major: int
    minor: int


MIN_VERSION = TmuxVersion(major=3, minor=2)


def parse_version(output: str) -> TmuxVersion | None:
    """Read `<digits>.<digits>` after `tmux ` or `tmux next-`; None if unreadable."""
    found = _VERSION.match(output.strip())
    if found is None:
        return None
    return TmuxVersion(major=int(found.group(1)), minor=int(found.group(2)))
