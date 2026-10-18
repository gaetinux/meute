"""The `claude` command line for a managed session."""

import shutil
from collections.abc import Mapping
from pathlib import Path

from meute.core.config_validate import PERMISSION_MODES
from meute.core.errors import InvalidInput
from meute.core.session import SessionId


def claude_argv(
    *,
    claude: Path,
    settings: Path,
    session_id: SessionId,
    permission_mode: str,
    title: str,
) -> tuple[str, ...]:
    """Build the argv; the title is glued to `--name=` so a leading dash stays data."""
    if permission_mode not in PERMISSION_MODES:
        message = f"unknown permission mode: {permission_mode}"
        raise InvalidInput(message)
    return (
        str(claude),
        "--settings",
        str(settings),
        "--session-id",
        session_id,
        "--permission-mode",
        permission_mode,
        f"--name={title}",
    )


def find_claude(environ: Mapping[str, str]) -> Path | None:
    """Locate the `claude` executable on the `PATH` of `environ`."""
    found = shutil.which("claude", path=environ.get("PATH"))
    return Path(found) if found else None
