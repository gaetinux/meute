"""Recording one Claude Code hook: cheap, bounded, and never migrating the database."""

from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from meute.core.db.connection import Database
from meute.core.db.hook_apply import apply_hook
from meute.core.errors import InvalidInput, NotFound
from meute.core.hooks import interpret_hook
from meute.core.json_types import parse_json_object
from meute.core.paths import Paths
from meute.core.session import SessionId, parse_session_id

MAX_STDIN_CHARS = 1024 * 1024
BUSY_TIMEOUT_MS = 200


def session_from_env(environ: Mapping[str, str]) -> SessionId | None:
    """Return the session named by `MEUTE_SESSION`, or None when it is missing or invalid."""
    try:
        return parse_session_id(environ.get("MEUTE_SESSION", ""))
    except InvalidInput:
        return None


def open_ingest_database(environ: Mapping[str, str], paths: Paths | None = None) -> Database | None:
    """Open the existing database briefly, or return None when there is none yet."""
    resolved = paths or Paths.from_env(environ, home=Path.home())
    try:
        return Database.open_existing(resolved.db_file, busy_timeout_ms=BUSY_TIMEOUT_MS)
    except FileNotFoundError:
        return None


def run_hook(event: str, stdin: TextIO, environ: Mapping[str, str]) -> None:
    """Record the hook `event` (its JSON payload on `stdin`) for the session `MEUTE_SESSION`.

    A missing, invalid or unknown session, or a missing database, is ignored silently.

    Raises:
        ValueError: the payload is too large, not valid JSON or not a JSON object.
        sqlite3.Error: the database is locked or unreadable (the caller logs it).
        MigrationError: the database schema is not the current one (never migrated here).
    """
    text = stdin.read(MAX_STDIN_CHARS + 1)  # always drained, so Claude never blocks on a pipe
    session_id = session_from_env(environ)
    if session_id is None:
        return
    if len(text) > MAX_STDIN_CHARS:
        message = "hook payload larger than 1 MiB"
        raise ValueError(message)
    payload = parse_json_object(text)
    effect = interpret_hook(event, payload)
    if effect is None:
        return
    database = open_ingest_database(environ)
    if database is None:
        return
    with database:
        try:
            apply_hook(database, session_id, event, effect)
        except NotFound:
            return
