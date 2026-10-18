"""Running `claude agents --json`, blocking or not."""

import os
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO

_MAX_OUTPUT = 1 << 20


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentsRun:
    """A started `claude agents --json`: the process and the file holding its output."""

    process: subprocess.Popen[bytes]
    output: IO[bytes]


def start_agents(claude: Path) -> AgentsRun | None:
    """Start `claude agents --json` in its own process group; `None` if it cannot start.

    The output goes to a file, so a large output never blocks the process.
    """
    output = tempfile.TemporaryFile()  # noqa: SIM115 — closed by `finish_agents`
    try:
        process = subprocess.Popen(  # noqa: S603 — fixed arguments, no shell
            [str(claude), "agents", "--json"],
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        output.close()
        return None
    return AgentsRun(process=process, output=output)


def kill_agents(run: AgentsRun) -> None:
    """Kill the whole process group of `run`, reap it and close its output."""
    try:
        os.killpg(run.process.pid, signal.SIGKILL)
    except OSError:
        run.process.kill()
    _ = run.process.wait()
    run.output.close()


def finish_agents(run: AgentsRun) -> str | None:
    """Return the output of a finished `run`, or `None` when it failed; closes the output."""
    try:
        if run.process.returncode != 0:
            return None
        _ = run.output.seek(0)
        return run.output.read(_MAX_OUTPUT).decode("utf-8", errors="replace")
    finally:
        run.output.close()


def run_agents(claude: Path, *, timeout: float = 2.0) -> str | None:
    """Run `claude agents --json` and return its output; `None` on failure, timeout or exit code."""
    run = start_agents(claude)
    if run is None:
        return None
    try:
        _ = run.process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_agents(run)
        return None
    return finish_agents(run)
