"""The test harness cleans up after itself: tmux servers, socket folders, child processes."""

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from process_support import survivors
from tmux_support import TestServer, clean_run_dir, kill_socket, sweep_stale_run_dirs


def _tmux() -> str:
    binary = shutil.which("tmux")
    assert binary is not None
    return binary


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_kill_socket_keeps_the_socket_when_the_kill_fails(tmp_path: Path) -> None:
    sock = tmp_path / "sock"
    sock.touch()
    killed = kill_socket("/bin/false", "meute-test-x", sock)
    assert killed is not None
    assert killed.returncode != 0
    assert sock.exists()


def test_kill_socket_returns_once_the_server_is_gone() -> None:
    server = TestServer.start()
    pid = int(server.tmux.run("display-message", "-p", "#{pid}"))
    server.stop()
    assert _gone(pid)
    assert server.socket_path is not None
    assert not server.socket_path.exists()


def test_tests_run_with_a_private_tmux_folder() -> None:
    folder = os.environ.get("TMUX_TMPDIR", "")
    found = re.fullmatch(r"/tmp/meute-tests-(\d+)", folder)  # noqa: S108 — the folder under test
    assert found is not None
    assert int(found[1]) in {os.getpid(), os.getppid()}
    assert Path(folder).is_dir()


def test_sweep_removes_only_folders_of_dead_runs(tmp_path: Path) -> None:
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    _ = dead.wait()
    for name in (f"meute-tests-{dead.pid}", f"meute-tests-{os.getpid()}", "meute-tests-x", "other"):
        (tmp_path / name).mkdir()
    sweep_stale_run_dirs(_tmux(), tmp_path)
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == sorted([f"meute-tests-{os.getpid()}", "meute-tests-x", "other"])


def test_clean_run_dir_kills_its_servers_and_removes_it() -> None:
    folder = Path(tempfile.mkdtemp(prefix="meute-clean-", dir="/tmp"))  # short socket path
    sock = folder / f"tmux-{os.getuid()}" / "meute-test-clean"
    sock.parent.mkdir()
    tmux = _tmux()
    _ = subprocess.run([tmux, "-S", str(sock), "-f", "/dev/null", "new-session", "-d"], check=True)
    pid = int(
        subprocess.run(
            [tmux, "-S", str(sock), "display-message", "-p", "#{pid}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    clean_run_dir(tmux, folder)
    assert _gone(pid)
    assert not folder.exists()


def test_survivors_finds_the_processes_a_test_left(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/x.py::left (call)")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert survivors("tests/x.py::left") == [child.pid]
        assert survivors("tests/x.py::lef") == []
    finally:
        child.send_signal(signal.SIGKILL)
        _ = child.wait()
    deadline = time.monotonic() + 5
    while survivors("tests/x.py::left") and time.monotonic() < deadline:
        time.sleep(0.01)
    assert survivors("tests/x.py::left") == []
