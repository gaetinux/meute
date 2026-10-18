"""Errors raised by the tmux adapter."""

from collections.abc import Sequence
from typing import override


class TmuxError(Exception):
    """Base class of every tmux adapter error."""


class NotInstalled(TmuxError):  # noqa: N818 — name fixed by the plan's API
    """The `tmux` binary is not on the `PATH`."""

    def __init__(self) -> None:
        super().__init__(
            "tmux not found: meute needs tmux 3.2 or later (for example: sudo apt install tmux)"
        )


class TooOld(TmuxError):  # noqa: N818 — name fixed by the plan's API
    """The installed tmux is older than the minimum supported version."""

    def __init__(self, found: str) -> None:
        super().__init__(f"tmux {found} is too old: meute needs tmux 3.2 or later")
        self.found = found


class CommandFailed(TmuxError):  # noqa: N818 — name fixed by the plan's API
    """A tmux command exited with a non-zero status."""

    def __init__(self, args: Sequence[str], stderr: str) -> None:
        self.message = f"tmux {' '.join(args)} failed: {stderr}"
        super().__init__(self.message)
        self.args = tuple(args)  # the tmux arguments, as the plan's API names them
        self.stderr = stderr

    @override
    def __str__(self) -> str:
        return self.message


class UnreadableOutput(TmuxError):  # noqa: N818 — name fixed by the plan's API
    """tmux printed something meute cannot interpret."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"unreadable tmux output: {detail}")
