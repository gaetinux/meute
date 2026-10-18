"""`meute ingest statusline`: record the samples, then print a status line."""

import contextlib
import json
import os
import pwd
import signal
import subprocess
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TextIO, TypeGuard

from meute.core.clock import local_zone
from meute.core.config import load_config
from meute.core.config_validate import Config
from meute.core.db.connection import Database
from meute.core.db.samples import record_metrics, record_quota
from meute.core.db.sessions import get_session
from meute.core.errors import InvalidInput, NotFound
from meute.core.instants import parse_zoned
from meute.core.paths import Paths
from meute.core.session import parse_session_id
from meute.core.statusline import StatuslineData, parse_statusline
from meute.core.statusline_render import render_statusline, statusline_width
from meute.ingest import drain
from meute.ingest.hook import BUSY_TIMEOUT_MS, MAX_STDIN_CHARS
from meute.ingest.log import log_error

_CHAIN_TIMEOUT_SECONDS = 1
_REAP_TIMEOUT_SECONDS = 0.2
_COMMAND = "ingest statusline"


def _is_object(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _parse(text: str) -> StatuslineData:
    loaded: object = json.loads(text)  # pyright: ignore[reportAny] — json.loads returns Any
    if not _is_object(loaded):
        message = "statusline payload is not a JSON object"
        raise ValueError(message)
    return parse_statusline({key: value for key, value in loaded.items() if isinstance(key, str)})


def _record(data: StatuslineData, paths: Paths, environ: Mapping[str, str]) -> None:
    try:
        session_id = parse_session_id(environ.get("MEUTE_SESSION", ""))
    except InvalidInput:
        return
    try:
        database = Database.open_existing(paths.db_file, busy_timeout_ms=BUSY_TIMEOUT_MS)
    except FileNotFoundError:
        return
    with database:
        try:
            get_session(database, session_id)
        except NotFound:
            return
        record_metrics(database, session_id, data)
        record_quota(database, data)


def _now(environ: Mapping[str, str]) -> datetime:
    frozen = environ.get("MEUTE_NOW")
    if frozen is not None:
        with contextlib.suppress(InvalidInput):
            return parse_zoned(frozen)
    return datetime.now(local_zone(environ))


def _tty_columns() -> int | None:
    try:
        return os.get_terminal_size(0).columns
    except OSError:
        return None


def _user() -> str:
    try:
        return pwd.getpwuid(os.geteuid()).pw_name
    except KeyError:
        return "?"


def _encode(payload: str) -> bytes:
    """Return the bytes read from stdin, original bytes included when they were not UTF-8."""
    try:
        return payload.encode("utf-8", errors="surrogateescape")
    except UnicodeEncodeError:
        return payload.encode("utf-8", errors="replace")


def _abandon(process: "subprocess.Popen[bytes]") -> None:
    """Kill the chain and let go of it at once, whatever descendants still hold its pipes."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)
    for pipe in (process.stdin, process.stdout):
        if pipe is not None:
            with contextlib.suppress(OSError):
                pipe.close()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=_REAP_TIMEOUT_SECONDS)


def _run_chain(chain: str, payload: str) -> str | None:
    """Return the output of the user's `chain` command, or None when it fails or is too slow.

    Takes about a second at most, whatever the command and its descendants do.
    """
    data = _encode(payload)  # before the child exists: nothing here can orphan it
    process = subprocess.Popen(  # noqa: S603 — the command is the user's own configuration
        ["/bin/sh", "-c", chain],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # its whole group can be killed on a timeout
    )
    try:
        output, _ = process.communicate(data, timeout=_CHAIN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _abandon(process)
        return None
    except BaseException:
        _abandon(process)  # an interruption must not orphan the child either
        raise
    text = output.decode("utf-8", errors="replace")
    return text if process.returncode == 0 and text.strip() else None


def _log(paths: Paths | None, error: Exception) -> None:
    if paths is not None:
        log_error(paths.state_dir, _COMMAND, error)


def run_statusline(stdin: TextIO, stdout: TextIO, environ: Mapping[str, str]) -> None:
    """Record the samples of the statusline JSON on `stdin`, then print the status line.

    The line is meute's own, or the output of the configured `chain` command. A problem on
    the way (unknown session, unreadable database or configuration) is logged and never
    stops the line from being printed. A payload that is not a JSON object under 1 MiB is
    logged and prints nothing.
    """
    raw = stdin.read(MAX_STDIN_CHARS + 1)  # first: nothing below may leave stdin unread
    config = Config()
    try:
        paths: Paths | None = Paths.from_env(environ, home=Path.home())
    except Exception:  # noqa: BLE001 — no home folder: no samples, no log, still a line
        paths = None
    try:
        if len(raw) > MAX_STDIN_CHARS:
            drain(stdin)
            message = "statusline payload larger than 1 MiB"
            raise ValueError(message)  # noqa: TRY301 — logged below like any other failure
        data = _parse(raw)
    except ValueError as error:  # not a statusline call: nothing sensible to print
        _log(paths, error)
        return
    if paths is not None:
        try:
            _record(data, paths, environ)
        except Exception as error:  # noqa: BLE001 — the line must still be printed
            _log(paths, error)
        try:
            config = load_config(paths.config_file)
        except Exception as error:  # noqa: BLE001 — the default line is better than none
            _log(paths, error)
    line = None
    if config.statusline.chain:
        try:
            line = _run_chain(config.statusline.chain, raw)
        except Exception as error:  # noqa: BLE001 — a broken chain falls back to meute's line
            _log(paths, error)
    if line is None:
        line = render_statusline(
            data,
            user=_user(),
            now=_now(environ),
            quotas=config.quotas,
            local=local_zone(environ),
            width=statusline_width(environ, _tty_columns),
        )
    stdout.write(line)
