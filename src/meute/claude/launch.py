"""The `claude` command line for a managed session."""

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import assert_never

from meute.claude.context_arg import ContextArg, ContextFile, ContextText
from meute.core.config_validate import PERMISSION_MODES
from meute.core.errors import InvalidInput
from meute.core.session import SessionId


def _context_options(context: ContextArg | None) -> tuple[str, ...]:
    match context:
        case None:
            return ()
        case ContextText(text=text):
            return ("--append-system-prompt", text)
        case ContextFile(path=path):
            return ("--append-system-prompt-file", str(path))
        case _:
            assert_never(context)


def claude_argv(  # noqa: PLR0913 — keyword-only: each argument is a distinct part of the command
    *,
    claude: Path,
    settings: Path,
    session_id: SessionId,
    permission_mode: str,
    title: str,
    resume: bool = False,
    mcp_config: Path | None = None,
    context: ContextArg | None = None,
) -> tuple[str, ...]:
    """Build the argv; the title is glued to `--name=` so a leading dash stays data.

    With `resume`, `--resume <id>` replaces `--session-id <id>`: Claude refuses both together.
    A `ContextText` is one argv word, handed to tmux as data and never through a shell.
    """
    if permission_mode not in PERMISSION_MODES:
        message = f"unknown permission mode: {permission_mode}"
        raise InvalidInput(message)
    return (
        str(claude),
        "--settings",
        str(settings),
        *(() if mcp_config is None else ("--mcp-config", str(mcp_config))),
        "--resume" if resume else "--session-id",
        session_id,
        "--permission-mode",
        permission_mode,
        *_context_options(context),
        f"--name={title}",
    )


def find_claude(environ: Mapping[str, str]) -> Path | None:
    """Locate the `claude` executable on the `PATH` of `environ`."""
    found = shutil.which("claude", path=environ.get("PATH"))
    return Path(found) if found else None
