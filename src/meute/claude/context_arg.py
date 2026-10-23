"""How the composed context reaches `claude`: as an argv word, or through a private file."""

from dataclasses import dataclass
from pathlib import Path

from meute.claude.settings import write_session_file
from meute.core.session import SessionId

# tmux refuses a command of about 16 KB, and the context travels in the argv of the pane's
# command: past this many UTF-8 bytes (leaving room for the rest of the line) it goes in a file.
CONTEXT_ARGV_LIMIT = 8_000


@dataclass(frozen=True, slots=True)
class ContextText:
    """The context itself, passed as `--append-system-prompt <text>`."""

    text: str


@dataclass(frozen=True, slots=True)
class ContextFile:
    """A private file holding the context, passed as `--append-system-prompt-file <path>`."""

    path: Path


type ContextArg = ContextText | ContextFile


def prepare_context(state_dir: Path, session_id: SessionId, text: str | None) -> ContextArg | None:
    """Choose how `text` is passed; a long one is written to `<session folder>/context.md`.

    A text holding a NUL, which no argv word can carry, goes to the file whatever its size.

    Any `context.md` left by an earlier, longer context is removed when it is no longer used.
    """
    stale = state_dir / "sessions" / session_id / "context.md"
    if text is None or ("\0" not in text and len(text.encode("utf-8")) <= CONTEXT_ARGV_LIMIT):
        stale.unlink(missing_ok=True)
        return None if text is None else ContextText(text)
    return ContextFile(write_session_file(state_dir, session_id, "context.md", text))
