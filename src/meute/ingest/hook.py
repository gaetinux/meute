"""Recording one Claude Code hook: cheap, bounded, and never migrating the database."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO, TypeGuard

from meute.core.db.connection import Database
from meute.core.db.hook_apply import apply_hook
from meute.core.errors import InvalidInput, NotFound
from meute.core.hooks import interpret_hook
from meute.core.paths import Paths
from meute.core.session import parse_session_id

MAX_STDIN_CHARS = 1024 * 1024
BUSY_TIMEOUT_MS = 200


def _is_object(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def run_hook(event: str, stdin: TextIO, environ: Mapping[str, str]) -> None:
    """Record the hook `event` (its JSON payload on `stdin`) for the session `MEUTE_SESSION`.

    A missing, invalid or unknown session, or a missing database, is ignored silently.

    Raises:
        ValueError: the payload is too large, not valid JSON or not a JSON object.
        sqlite3.Error: the database is locked or unreadable (the caller logs it).
        MigrationError: the database schema is not the current one (never migrated here).
    """
    text = stdin.read(MAX_STDIN_CHARS + 1)  # always drained, so Claude never blocks on a pipe
    try:
        session_id = parse_session_id(environ.get("MEUTE_SESSION", ""))
    except InvalidInput:
        return
    if len(text) > MAX_STDIN_CHARS:
        message = "hook payload larger than 1 MiB"
        raise ValueError(message)
    loaded: object = json.loads(text)  # pyright: ignore[reportAny] — json.loads returns Any
    if not _is_object(loaded):
        message = "hook payload is not a JSON object"
        raise ValueError(message)
    payload = {key: value for key, value in loaded.items() if isinstance(key, str)}
    effect = interpret_hook(event, payload)
    if effect is None:
        return
    paths = Paths.from_env(environ, home=Path.home())
    try:
        database = Database.open_existing(paths.db_file, busy_timeout_ms=BUSY_TIMEOUT_MS)
    except FileNotFoundError:
        return
    with database:
        try:
            apply_hook(database, session_id, event, effect)
        except NotFound:
            return
