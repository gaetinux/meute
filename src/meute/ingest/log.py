"""The ingest failure log: bounded, rotated, and never a source of failure."""

import os
from datetime import datetime
from pathlib import Path

from meute.core.instants import to_db, utc_now
from meute.core.text import one_line

_MAX_BYTES = 1024 * 1024
_MESSAGE_MAX = 200
_NAME = "ingest.log"


def log_failure(state_dir: Path, command: str, error: BaseException, now: datetime) -> None:
    """Append `<instant> <command> <ErrorType>: <message>` to `<state_dir>/ingest.log`.

    The message is one line of 200 characters at most. The file is rotated to
    `ingest.log.1` once it exceeds 1 MiB. Any failure to write is swallowed.
    """
    line = (
        f"{to_db(now)} {one_line(command, _MESSAGE_MAX)} "
        f"{type(error).__name__}: {one_line(str(error), _MESSAGE_MAX)}\n"
    )
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / _NAME
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            path.replace(state_dir / f"{_NAME}.1")
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8", errors="replace") as handle:
            handle.write(line)
    except Exception:  # noqa: BLE001 — the log must never disturb Claude Code
        return


def log_error(state_dir: Path, command: str, error: BaseException) -> None:
    """Log `error` now, as `log_failure` does."""
    log_failure(state_dir, command, error, utc_now())
