"""Running git safely in repositories that Claude may have tampered with.

Reads never run a command that the repository's configuration can choose (`core.fsmonitor`,
external diff drivers, `textconv`), never take the index lock and never prompt. Writes keep the
user's hooks but not `core.fsmonitor`. Every command runs under a timeout, and git with every
process it started is killed when the timeout expires.
"""

import os
import shutil
import signal
import subprocess
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path

_NO_FSMONITOR = ("-c", "core.fsmonitor=false")
_DIFF_GUARD = ("--no-ext-diff", "--no-textconv")
_GUARD_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
_MESSAGE_LIMIT = 200


class GitError(Exception):
    """A git command failed; the message is ready to show."""


def find_git(environ: Mapping[str, str]) -> Path | None:
    """The git binary on the `PATH` of `environ`; None without a `PATH`."""
    path = environ.get("PATH")
    if path is None:
        return None
    found = shutil.which("git", path=path)
    return None if found is None else Path(found)


def _target(folder: Path) -> tuple[str, str]:
    if not folder.is_absolute():
        msg = f"git needs an absolute folder: {folder}"
        raise ValueError(msg)
    return ("-C", str(folder))


def read_args(folder: Path, args: Sequence[str]) -> tuple[str, ...]:
    """The guarded argv of a read command in `folder`, without the git binary."""
    command = tuple(args)
    if command[:1] == ("diff",):
        command = ("diff", *_DIFF_GUARD, *command[1:])
    return (*_NO_FSMONITOR, "--no-optional-locks", *_target(folder), *command)


def _environment(environ: Mapping[str, str]) -> dict[str, str]:
    return {**environ, **_GUARD_ENV}


def _start(git: Path, argv: Sequence[str], environ: Mapping[str, str]) -> subprocess.Popen[bytes]:
    try:
        return subprocess.Popen(  # noqa: S603 — fixed argv, no shell
            [str(git), *argv],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_environment(environ),
            start_new_session=True,  # its own process group, killed as a whole
        )
    except FileNotFoundError as error:
        msg = "git not found"
        raise GitError(msg) from error
    except OSError as error:
        msg = f"git: {error.strerror}"
        raise GitError(msg) from error


def _kill(process: subprocess.Popen[bytes]) -> None:
    """Kill git's process group and reap git, without waiting on pipes an escapee may hold."""
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    for pipe in (process.stdout, process.stderr):
        if pipe is not None:
            pipe.close()
    process.wait()


def _first_line(stderr: bytes) -> str:
    lines = stderr.decode("utf-8", errors="replace").strip().splitlines()
    return lines[0][:_MESSAGE_LIMIT] if lines else ""


def _run(git: Path, argv: Sequence[str], timeout: float, environ: Mapping[str, str]) -> str:
    process = _start(git, argv, environ)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _kill(process)
        msg = f"git timed out after {timeout:g} s"
        raise GitError(msg) from error
    if process.returncode != 0:
        msg = f"git: {_first_line(stderr) or f'exit status {process.returncode}'}"
        raise GitError(msg)
    return stdout.decode("utf-8", errors="replace")


def read_git(
    git: Path, folder: Path, args: Sequence[str], *, timeout: float, environ: Mapping[str, str]
) -> str:
    """Run a guarded read command in `folder` and return its output.

    Raises:
        GitError: git is missing, failed or did not finish within `timeout` seconds.
    """
    return _run(git, read_args(folder, args), timeout, environ)


def start_read(
    git: Path, folder: Path, args: Sequence[str], *, environ: Mapping[str, str]
) -> subprocess.Popen[bytes]:
    """Start the same command as `read_git` without waiting for it.

    Raises:
        GitError: git is missing.
    """
    return _start(git, read_args(folder, args), environ)


def write_git(
    git: Path, repo: Path, args: Sequence[str], *, timeout: float, environ: Mapping[str, str]
) -> str:
    """Run a write command in `repo`, hooks kept, and return its output.

    Raises:
        GitError: git is missing, failed or did not finish within `timeout` seconds.
    """
    return _run(git, (*_NO_FSMONITOR, *_target(repo), *args), timeout, environ)
