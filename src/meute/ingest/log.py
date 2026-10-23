"""The failure logs (`ingest.log`, `mcp.log`): bounded, rotated, never a source of failure."""

import os
from datetime import datetime
from pathlib import Path

from meute.core.instants import to_db, utc_now
from meute.core.text import one_line

_MAX_BYTES = 1024 * 1024
_MESSAGE_MAX = 200
_NAME = "ingest.log"


def log_failure(
    state_dir: Path, command: str, error: BaseException, now: datetime, *, name: str = _NAME
) -> None:
    """Append `<instant> <command> <ErrorType>: <message>` to `<state_dir>/<name>`.

    The message is one line of 200 characters at most. The file is rotated to
    `<name>.1` once it exceeds 1 MiB. Any failure, even to build the line, is swallowed.
    """
    try:
        line = (
            f"{to_db(now)} {one_line(command, _MESSAGE_MAX)} "
            f"{type(error).__name__}: {one_line(str(error), _MESSAGE_MAX)}\n"
        )
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = state_dir / name
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            path.replace(state_dir / f"{name}.1")
        descriptor = os.open(
            path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
        )
        with os.fdopen(descriptor, "a", encoding="utf-8", errors="replace") as handle:
            handle.write(line)
    except Exception:  # noqa: BLE001 — the log must never disturb Claude Code
        return


def log_error(state_dir: Path, command: str, error: BaseException, *, name: str = _NAME) -> None:
    """Log `error` now, as `log_failure` does."""
    log_failure(state_dir, command, error, utc_now(), name=name)
