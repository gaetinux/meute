"""Reading the Git state of the board's folders in the background, never waiting on git.

Each folder runs as a pipeline of non-blocking stages: the filter driver lookup, then
`status` and `diff --numstat` with those drivers neutralised. A stage still running
`kill_after` seconds after it started is killed, and its folder is left out of the round.
"""

import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from itertools import islice
from pathlib import Path
from typing import IO

from meute.core.git_state import GitState, parse_numstat, parse_status_v2
from meute.git.run import (
    GitError,
    has_exited,
    kill_read,
    lookup_filters,
    start_filter_lookup,
    start_read_with,
)

_STATUS = ("status", "--porcelain=v2", "--branch")
_NUMSTAT = ("diff", "--numstat", "HEAD")
_CHUNK = 65536


def _drain(pipe: IO[bytes] | None, into: bytearray) -> None:
    """Append what `pipe` holds to `into`, without waiting for more."""
    if pipe is None:
        return
    while True:
        try:
            chunk = os.read(pipe.fileno(), _CHUNK)
        except BlockingIOError:
            return
        if not chunk:
            return
        into += chunk


class _Run:
    """A git process, the output it wrote so far and when it started."""

    def __init__(self, process: subprocess.Popen[bytes], started_at: float) -> None:
        self.process = process
        self.started_at = started_at
        self.out = bytearray()
        for pipe in (process.stdout, process.stderr):
            if pipe is not None:
                os.set_blocking(pipe.fileno(), False)

    def step(self) -> bool:
        """Read what git wrote, so it never blocks on a full pipe; return whether it exited."""
        exited = has_exited(self.process)  # first: all its output is then in the pipes
        _drain(self.process.stdout, self.out)
        _drain(self.process.stderr, bytearray())  # unused, but it must not fill up
        return exited

    def finish(self) -> tuple[int, bytes]:
        """Reap git, killing what it left behind; return its exit status and output."""
        return kill_read(self.process), bytes(self.out)


class _Folder:
    """One folder of a round: its lookup, then its two reads."""

    def __init__(self, folder: Path, lookup: _Run) -> None:
        self.folder = folder
        self.runs: tuple[_Run, ...] = (lookup,)
        self.looked_up = False

    def kill(self) -> None:
        for run in self.runs:
            _ = kill_read(run.process)
        self.runs = ()


def _chosen(folders: Sequence[Path], limit: int) -> list[Path]:
    """The first `limit` distinct folders that are absolute and exist, in order.

    No folder after the `limit`-th one found is looked at on disk.
    """
    distinct = dict.fromkeys(folder for folder in folders if folder.is_absolute())
    return list(islice((folder for folder in distinct if folder.is_dir()), limit))


class GitPoller:
    """Starts a round at most every `every` seconds and harvests it without ever waiting."""

    def __init__(  # noqa: PLR0913 — the poller's knobs, all but two with defaults
        self,
        git: Path | None,
        environ: Mapping[str, str],
        *,
        every: float = 10.0,
        kill_after: float = 5.0,
        monotonic: Callable[[], float] = time.monotonic,
        limit: int = 40,
    ) -> None:
        self._git = git
        self._environ = environ
        self._every = every
        self._kill_after = kill_after
        self._monotonic = monotonic
        self._limit = limit
        self._round: list[_Folder] | None = None
        self._found: dict[Path, GitState] = {}
        self._started_at: float | None = None

    def poll(self, folders: Sequence[Path]) -> Mapping[Path, GitState] | None:
        """Return the states of a finished round, or `None` while there is none; never blocks.

        A new round over `folders` starts when none runs and `every` seconds have passed.
        """
        now = self._monotonic()
        result = self._harvest(now)
        if (
            self._git is not None
            and self._round is None
            and (self._started_at is None or now - self._started_at >= self._every)
        ):
            self._started_at = now
            self._found = {}
            self._round = [
                job
                for folder in _chosen(folders, self._limit)
                if (job := self._start(self._git, folder, now)) is not None
            ]
        return result

    def close(self) -> None:
        """Kill the commands still running, if any."""
        for job in self._round or ():
            job.kill()
        self._round = None

    def _start(self, git: Path, folder: Path, now: float) -> _Folder | None:
        try:
            return _Folder(
                folder, _Run(start_filter_lookup(git, folder, environ=self._environ), now)
            )
        except GitError:
            return None

    def _harvest(self, now: float) -> Mapping[Path, GitState] | None:
        git = self._git
        if self._round is None or git is None:
            return None
        self._round = [job for job in self._round if not self._step(git, job, now)]
        if self._round:
            return None
        self._round = None
        return self._found

    def _step(self, git: Path, job: _Folder, now: float) -> bool:
        """Move `job` on; return whether it is over."""
        exited = [run.step() for run in job.runs]
        if not all(exited):
            late = any(
                now - run.started_at > self._kill_after
                for run, done in zip(job.runs, exited, strict=True)
                if not done
            )
            if late:
                job.kill()
            return late
        results = [run.finish() for run in job.runs]
        job.runs = ()
        if job.looked_up:
            self._record(job.folder, results)
            return True
        job.looked_up = True
        return not self._read(git, job, results[0], now)

    def _read(self, git: Path, job: _Folder, lookup: tuple[int, bytes], now: float) -> bool:
        """Start the two reads of `job` after its lookup; return whether they started."""
        try:
            filters = lookup_filters(*lookup, b"")
            for args in (_STATUS, _NUMSTAT):  # one by one: a failed start kills the first
                started = start_read_with(git, job.folder, args, filters, environ=self._environ)
                job.runs = (*job.runs, _Run(started, now))
        except GitError:  # a filter name it cannot neutralise, or git is gone
            job.kill()
            return False
        return True

    def _record(self, folder: Path, results: Sequence[tuple[int, bytes]]) -> None:
        (status_code, status), (diff_code, diff) = results
        state = parse_status_v2(_text(status)) if status_code == 0 else None
        if state is None:  # outside Git, or git failed
            return
        added, removed = parse_numstat(_text(diff)) if diff_code == 0 else (0, 0)  # unborn HEAD
        self._found[folder] = replace(state, added=added, removed=removed)


def _text(output: bytes) -> str:
    return output.decode("utf-8", errors="replace")
