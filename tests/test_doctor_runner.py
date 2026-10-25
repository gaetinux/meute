"""The tool runner of `meute doctor`: nothing is left running behind it."""

import os
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path

import pytest

from doctor_support import real
from meute.cli.doctor import TimedOut, tool_output
from support import wait_until
from test_git_run import is_alive


def _script(tmp_path: Path, body: str) -> Path:
    folder = tmp_path / "bin"
    folder.mkdir(exist_ok=True)
    script = folder / "tool"
    _ = script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(0o755)
    return folder


def test_ctrl_c_during_a_slow_tool_kills_its_group_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "child.pid"
    folder = _script(tmp_path, f"{real('sleep')} 30 & echo $! > {pid_file}; wait")

    def interrupted(_process: object, timeout: float | None = None) -> tuple[bytes, bytes]:
        del timeout
        wait_until("the child to start", lambda: pid_file.exists() and bool(pid_file.read_text()))
        raise KeyboardInterrupt

    with monkeypatch.context() as patched:
        patched.setattr(subprocess.Popen, "communicate", interrupted)
        with pytest.raises(KeyboardInterrupt):
            _ = tool_output(["tool"], {"PATH": str(folder)})
    child = int(pid_file.read_text())
    wait_until("the child to die", lambda: not is_alive(child), timeout=3)


def test_a_mute_tool_times_out_and_its_group_is_killed(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    folder = _script(tmp_path, f"{real('sleep')} 30 & echo $! > {pid_file}; wait")
    assert tool_output(["tool"], {"PATH": str(folder)}, timeout=0.3) == TimedOut()
    child = int(pid_file.read_text())
    wait_until("the child to die", lambda: not is_alive(child), timeout=3)


def test_a_grandchild_escaping_the_group_does_not_hang_the_runner(tmp_path: Path) -> None:
    pid_file = tmp_path / "escaped.pid"
    escape = f"{real('setsid')} {real('sleep')} 20 & echo $! > {pid_file}; wait"
    folder = _script(tmp_path, escape)
    started = time.monotonic()
    try:
        output = tool_output(["tool"], {"PATH": str(folder)}, timeout=0.3)
        elapsed = time.monotonic() - started
    finally:
        with suppress(OSError, ValueError):
            os.kill(int(pid_file.read_text()), signal.SIGKILL)
    assert output == TimedOut()
    assert elapsed < 2
