"""Who does something, and through which channel."""

from dataclasses import dataclass
from enum import Enum


class Author(Enum):
    """The kind of author of a change."""

    USER = "user"
    CLAUDE = "claude"
    SYSTEM = "system"


class Channel(Enum):
    """The interface a change came through."""

    TUI = "tui"
    CLI = "cli"
    MCP = "mcp"
    FORGE = "forge"


@dataclass(frozen=True, slots=True, kw_only=True)
class Actor:
    """An author acting through a channel, possibly from a Claude session."""

    author: Author
    channel: Channel
    session_id: str | None = None
