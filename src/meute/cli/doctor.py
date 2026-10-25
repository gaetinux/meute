"""`meute doctor`: probe the tools, the files and the tmux server, creating nothing."""

import os
import shutil
import sqlite3
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from meute.cli.tmux_env import DEFAULT_SOCKET
from meute.core.config import load_config
from meute.core.db.schema import SCHEMA_VERSION, read_schema_version
from meute.core.doctor import (
    NOTE_CHECK,
    Check,
    CheckLevel,
    claude_check,
    database_check,
    git_check,
    options_check,
    timeout_check,
    tmux_check,
)
from meute.core.errors import ConfigError
from meute.core.paths import Paths, shown_path
from meute.core.text import printable
from meute.git.run import kill_read
from meute.tmux.client import Tmux

TIMEOUT_SECONDS = 5  # what a tool has to answer `meute doctor`


@dataclass(frozen=True, slots=True)
class TimedOut:
    """The program did not answer within the delay; it was killed."""


type ToolOutput = subprocess.CompletedProcess[str] | TimedOut | None


def tool_output(
    argv: Sequence[str], environ: Mapping[str, str], *, timeout: float = TIMEOUT_SECONDS
) -> ToolOutput:
    """Run `argv` without a shell, its program looked up on the `PATH` of `environ`.

    Returns None when the program is not found, `TimedOut` when it does not answer within
    `timeout` seconds (its whole process group is then killed), else the result decoded as
    UTF-8 with replacement characters, whatever its exit code.
    """
    found = shutil.which(argv[0], path=environ.get("PATH"))
    if found is None:
        return None
    command = [found, *argv[1:]]
    try:
        process = subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(environ),
            start_new_session=True,  # its own process group: a child holding the pipes dies too
        )
    except OSError as error:
        return subprocess.CompletedProcess(command, 126, "", str(error))
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException as error:  # a timeout, or Ctrl-C during a slow tool: nothing left behind
        _ = kill_read(process)
        if isinstance(error, subprocess.TimeoutExpired):
            return TimedOut()
        raise
    return subprocess.CompletedProcess(
        command,
        process.returncode,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


def _failure(name: str, shown: str, reason: str) -> Check:
    return Check(level=CheckLevel.FAIL, name=name, text=printable(f"{shown}: {reason}"))


type _Done = subprocess.CompletedProcess[str] | None  # None: the tool was not found


def _probe(
    name: str, argv: Sequence[str], environ: Mapping[str, str], judge: Callable[[_Done], Check]
) -> Check:
    """Run `argv` and judge its result; a tool that does not answer within 5 s fails `name`."""
    output = tool_output(argv, environ)
    if isinstance(output, TimedOut):
        return timeout_check(argv[0], name=name)
    return judge(output)


def _tool_check(
    name: str, argv: Sequence[str], judge: Callable[[str | None], Check], environ: Mapping[str, str]
) -> Check:
    return _probe(name, argv, environ, lambda done: judge(None if done is None else done.stdout))


def _config(path: Path, home: Path) -> Check:
    shown = shown_path(path, home)
    try:
        _ = load_config(path)
    except ConfigError as error:
        return Check(level=CheckLevel.FAIL, name="config", text=printable(str(error)))
    except OSError as error:
        return _failure("config", shown, error.strerror or str(error))  # strerror: no raw path
    text = shown if path.exists() else f"{shown} (absent: defaults are used)"
    return Check(level=CheckLevel.OK, name="config", text=text)


def _database(path: Path, home: Path) -> Check:
    shown = shown_path(path, home)
    try:
        version = read_schema_version(path)
    except OSError as error:
        return _failure("database", shown, error.strerror or str(error))  # strerror: no raw path
    except sqlite3.Error as error:
        return _failure("database", shown, str(error))
    return database_check(shown, version, SCHEMA_VERSION)


def _writable_folder(path: Path) -> bool:
    """Whether `path`, or its first existing parent when absent, is writable and searchable.

    A parent that cannot be searched makes `exists` raise: the folder is then not writable.
    """
    try:
        existing = next((folder for folder in (path, *path.parents) if folder.exists()), path)
    except OSError:
        return False
    return os.access(existing, os.W_OK | os.X_OK)


def _state(path: Path, home: Path) -> Check:
    shown = shown_path(path, home)
    if _writable_folder(path):
        return Check(level=CheckLevel.OK, name="state", text=shown)
    return Check(level=CheckLevel.FAIL, name="state", text=f"{shown}: not writable")


def _server_line(prefix: str, done: _Done) -> Check:
    if done is None:
        return tmux_check(None, name="server")
    if done.returncode != 0:
        text = f"{prefix}: not running (meute starts it)"
    else:
        count = len([name for name in done.stdout.splitlines() if name])
        text = f"{prefix}: running, {count} session{'' if count == 1 else 's'}"
    return Check(level=CheckLevel.OK, name="server", text=text)


def _server(environ: Mapping[str, str]) -> Check:
    socket = environ.get("MEUTE_TMUX_SOCKET") or DEFAULT_SOCKET
    argv = [*Tmux(socket=socket).base_args(), "list-sessions", "-F", "#{session_name}"]
    prefix = f"tmux server {printable(socket)}"
    return _probe("server", argv, environ, lambda done: _server_line(prefix, done))


def run_doctor(environ: Mapping[str, str], *, home: Path) -> list[Check]:
    """Run every check of `meute doctor`, in the order of its output; creates nothing.

    A failed tmux check skips the `server` line; a failed claude check (not
    found, or no answer to `--version`) skips `options`.
    """
    paths = Paths.from_env(environ, home=home)
    tmux = _tool_check("tmux", ["tmux", "-V"], tmux_check, environ)
    git = _tool_check("git", ["git", "--version"], git_check, environ)
    claude = _tool_check("claude", ["claude", "--version"], claude_check, environ)
    checks = [tmux, git, claude]
    if claude.level is not CheckLevel.FAIL:
        help_check = _tool_check(
            "options", ["claude", "--help"], lambda text: options_check(text or ""), environ
        )
        checks.append(help_check)
    checks += [
        _config(paths.config_file, home),
        _database(paths.db_file, home),
        _state(paths.state_dir, home),
    ]
    if tmux.level is not CheckLevel.FAIL:
        checks.append(_server(environ))
    checks.append(NOTE_CHECK)
    return checks
