"""Running git safely in repositories that Claude may have tampered with.

Reads never run a command that the repository's configuration can choose:

- `core.fsmonitor` is turned off;
- `diff` gets `--no-ext-diff` and `--no-textconv` (external diff drivers, `textconv`);
- every configured filter driver is emptied (`clean`, `process`, not `required`), after a
  lookup with `git config`, which runs nothing; a name `-c` cannot express is refused;
- `status` and `diff` get `--ignore-submodules=all`, so no submodule configuration is used;
- a partial clone never fetches a missing object from its promisor remote (`GIT_NO_LAZY_FETCH`,
  and `protocol.allow=never` for git before 2.45), so no transport such as `core.sshCommand` runs.

Reads also never take the index lock and never prompt. Writes keep the user's hooks but not
`core.fsmonitor`. Every command runs under a timeout, and git with every process it started is
killed when the timeout expires.
"""

import os
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path

_NO_FSMONITOR = ("-c", "core.fsmonitor=false")
_NO_TRANSPORT = ("-c", "protocol.allow=never")
_DIFF_GUARD = ("--no-ext-diff", "--no-textconv")
_NO_SUBMODULES = "--ignore-submodules=all"
_FILTER_LOOKUP = ("config", "--null", "--get-regexp", r"^filter\.")
_GUARD_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1"}
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


def read_args(folder: Path, args: Sequence[str], filters: Sequence[str] = ()) -> tuple[str, ...]:
    """The guarded argv of a read command in `folder`, without the git binary.

    `filters` are the filter driver names to neutralise (see `filter_drivers`).
    """
    command = tuple(args)
    if command[:1] == ("diff",):
        command = ("diff", *_DIFF_GUARD, _NO_SUBMODULES, *command[1:])
    elif command[:1] == ("status",):
        command = ("status", _NO_SUBMODULES, *command[1:])
    neutralised = tuple(
        word
        for name in filters
        for key in ("clean=", "process=", "required=false")
        for word in ("-c", f"filter.{name}.{key}")
    )
    guards = (*_NO_FSMONITOR, *_NO_TRANSPORT, *neutralised, "--no-optional-locks")
    return (*guards, *_target(folder), *command)


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


def has_exited(process: subprocess.Popen[bytes]) -> bool:
    """Whether git has exited, without reaping it: its process group stays safe to kill."""
    if process.returncode is not None:
        return True
    try:
        exited = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError:  # already reaped
        return True
    return exited is not None


def kill_read(process: subprocess.Popen[bytes]) -> int:
    """Kill git's process group, close its pipes and reap git; return its exit status.

    It never waits on pipes an escaped child may hold. A status below 0 is the signal that
    killed git.
    """
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    for pipe in (process.stdout, process.stderr):
        if pipe is not None:
            pipe.close()
    return process.wait()


def _failure(returncode: int, stderr: bytes) -> GitError:
    lines = stderr.decode("utf-8", errors="replace").strip().splitlines()
    first = lines[0][:_MESSAGE_LIMIT] if lines else f"exit status {returncode}"
    return GitError(f"git: {first}")


def _timed_out(timeout: float) -> GitError:
    return GitError(f"git timed out after {timeout:g} s")


def _communicate(
    git: Path,
    argv: Sequence[str],
    timeout: float,
    environ: Mapping[str, str],
    *,
    shown: float | None = None,
) -> tuple[int, bytes, bytes]:
    """Run git for at most `timeout` seconds; a timeout names `shown` seconds, or `timeout`."""
    process = _start(git, argv, environ)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        _ = kill_read(process)
        raise _timed_out(timeout if shown is None else shown) from error
    return process.returncode, stdout, stderr


def _run(
    git: Path,
    argv: Sequence[str],
    timeout: float,
    environ: Mapping[str, str],
    *,
    shown: float | None = None,
) -> str:
    returncode, stdout, stderr = _communicate(git, argv, timeout, environ, shown=shown)
    if returncode != 0:
        raise _failure(returncode, stderr)
    return stdout.decode("utf-8", errors="replace")


def filter_names(output: str) -> tuple[str, ...]:
    """The distinct filter driver names in `git config --null --get-regexp` output, in order.

    Raises:
        GitError: a name that `-c` cannot express (it holds `=`), so it cannot be neutralised.
    """
    names: dict[str, None] = {}
    for record in output.split("\0"):
        key = record.partition("\n")[0]
        # `filter.<name>.<key>`, `<name>` possibly empty; `filter.<key>` names no driver.
        name, dot, _ = key.removeprefix("filter.").rpartition(".")
        if not key.startswith("filter.") or not dot:
            continue
        if "=" in name:
            msg = "git: unsupported filter driver name"
            raise GitError(msg)
        names[name] = None
    return tuple(names)


def lookup_filters(returncode: int, stdout: bytes, stderr: bytes) -> tuple[str, ...]:
    """The filter driver names from a finished lookup (see `start_filter_lookup`).

    Raises:
        GitError: the lookup failed or reported a name it cannot neutralise.
    """
    if returncode == 1:  # no matching key
        return ()
    if returncode != 0:
        raise _failure(returncode, stderr)
    return filter_names(stdout.decode("utf-8", errors="replace"))


def filter_drivers(
    git: Path, folder: Path, *, timeout: float, environ: Mapping[str, str]
) -> tuple[str, ...]:
    """The filter drivers configured for `folder`, read without running any of them.

    Raises:
        GitError: git is missing, failed, timed out or reported a name it cannot neutralise.
    """
    return lookup_filters(*_communicate(git, read_args(folder, _FILTER_LOOKUP), timeout, environ))


def start_filter_lookup(
    git: Path, folder: Path, *, environ: Mapping[str, str]
) -> subprocess.Popen[bytes]:
    """Start the filter driver lookup of `filter_drivers` without waiting for it.

    Raises:
        GitError: git is missing.
    """
    return _start(git, read_args(folder, _FILTER_LOOKUP), environ)


def start_read_with(
    git: Path,
    folder: Path,
    args: Sequence[str],
    filters: Sequence[str],
    *,
    environ: Mapping[str, str],
) -> subprocess.Popen[bytes]:
    """Start a guarded read command in `folder`, neutralising the given filter drivers.

    Raises:
        GitError: git is missing.
    """
    return _start(git, read_args(folder, args, filters), environ)


def read_git(
    git: Path, folder: Path, args: Sequence[str], *, timeout: float, environ: Mapping[str, str]
) -> str:
    """Run a guarded read command in `folder` and return its output.

    The filter driver lookup and the command share the `timeout`: the command gets what the
    lookup left.

    Raises:
        GitError: git is missing, failed or did not finish within `timeout` seconds.
    """
    deadline = time.monotonic() + timeout
    filters = filter_drivers(git, folder, timeout=timeout, environ=environ)
    left = deadline - time.monotonic()
    if left <= 0:
        raise _timed_out(timeout)
    return _run(git, read_args(folder, args, filters), left, environ, shown=timeout)


def write_git(
    git: Path, repo: Path, args: Sequence[str], *, timeout: float, environ: Mapping[str, str]
) -> str:
    """Run a write command in `repo`, hooks kept, and return its output.

    Raises:
        GitError: git is missing, failed or did not finish within `timeout` seconds.
    """
    return _run(git, (*_NO_FSMONITOR, *_target(repo), *args), timeout, environ)
