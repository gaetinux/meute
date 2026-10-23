"""Test configuration: hypothesis profiles chosen by `HYPOTHESIS_PROFILE`."""

import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Generator, Mapping
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from hypothesis import settings

from meute.core.db.connection import Database
from meute.tmux.client import Tmux
from process_support import command_line, survivors
from support import FIXED
from tmux_support import (
    RUN_DIR_PREFIX,
    TestServer,
    clean_run_dir,
    kill_socket,
    sweep_stale_run_dirs,
)

pytest_plugins = ["git_support"]  # the `git_repo` fixture

settings.register_profile("dev", max_examples=100)
settings.register_profile("ci", max_examples=1000)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

_RUN_ROOT = Path("/tmp")  # noqa: S108 — short: tmux socket paths must stay under 100 characters
_RUN_DIR_KEY = pytest.StashKey[Path]()


def pytest_configure(config: pytest.Config) -> None:
    """On the controller, give the run its own tmux folder, inherited by workers and meute."""
    if hasattr(config, "workerinput"):
        return
    binary = shutil.which("tmux")
    if binary is not None:
        sweep_stale_run_dirs(binary, _RUN_ROOT)
    folder = _RUN_ROOT / f"{RUN_DIR_PREFIX}{os.getpid()}"
    folder.mkdir(mode=0o700, exist_ok=True)
    config.stash[_RUN_DIR_KEY] = folder
    os.environ["TMUX_TMPDIR"] = str(folder)


def pytest_unconfigure(config: pytest.Config) -> None:
    """On the controller, kill every tmux server left in the run's folder and remove it."""
    folder = config.stash.get(_RUN_DIR_KEY, None)
    binary = shutil.which("tmux")
    if folder is not None and binary is not None:
        clean_run_dir(binary, folder)


_SURVIVOR_GRACE_SECONDS = 3.0
# Tests whose process escapes on purpose: their survivors are killed without failing them.
_ESCAPING_ON_PURPOSE = frozenset(
    {
        "tests/test_ingest_statusline.py::test_chain_with_an_escaped_descendant_still_returns_quickly",
    }
)


@pytest.fixture(autouse=True)
def no_process_survives() -> Generator[None]:
    """Fail a test whose processes outlive it (tmux panes get a grace period); kill them."""
    nodeid = os.environ.get("PYTEST_CURRENT_TEST", "").rpartition(" (")[0]
    yield
    if not nodeid:
        return
    deadline = time.monotonic() + _SURVIVOR_GRACE_SECONDS
    while (left := survivors(nodeid)) and time.monotonic() < deadline:
        time.sleep(0.02)
    described = [f"{pid} {command_line(pid)}" for pid in left]
    for pid in left:
        with suppress(OSError):
            os.kill(pid, signal.SIGKILL)
    if described and nodeid not in _ESCAPING_ON_PURPOSE:
        pytest.fail(f"processes outlived the test: {described}", pytrace=False)


@pytest.fixture
def db() -> Generator[Database]:
    """An in-memory database with a fixed clock, closed after the test."""
    with Database.in_memory(clock=lambda: FIXED) as database:
        yield database


@pytest.fixture
def file_db(tmp_path: Path) -> Generator[tuple[Database, Path]]:
    """A file database with a fixed clock, and its path, closed after the test."""
    path = tmp_path / "meute.db"
    with Database.open(path, busy_timeout_ms=1000, clock=lambda: FIXED) as database:
        yield database, path


FAKE_CLAUDE_DIR = Path(__file__).parent / "fake_claude"  # first in PATH: never the real claude


@dataclass(frozen=True, slots=True, kw_only=True)
class Sandbox:
    """A throw-away home where `python -m meute` runs with a frozen clock."""

    root: Path
    tmux_socket: str

    def run(
        self, *args: str, env: Mapping[str, str] | None = None, stdin: str = ""
    ) -> subprocess.CompletedProcess[str]:
        """Run meute with `args` in a subprocess and capture its output."""
        environ = {key: value for key, value in os.environ.items() if key != "MEUTE_SESSION"}
        environ["PATH"] = f"{FAKE_CLAUDE_DIR}:{environ.get('PATH', '')}"
        environ |= {
            "HOME": str(self.root / "home"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_STATE_HOME": str(self.root / "state"),
            "MEUTE_NOW": "2026-10-14T10:30[Europe/Paris]",
            "MEUTE_TMUX_SOCKET": self.tmux_socket,
            "SHELL": "/bin/sh",
        }
        environ |= env or {}
        return subprocess.run(
            [sys.executable, "-m", "meute", *args],
            input=stdin,
            capture_output=True,
            text=True,
            env=environ,
            check=False,
        )

    def tmux(self) -> Tmux:
        """A client of the sandbox's throw-away tmux server."""
        return Tmux(socket=self.tmux_socket, config_file=None)

    def db(self) -> AbstractContextManager[Database]:
        """Open the sandbox database with the fixed clock."""
        return Database.open(
            self.root / "data/meute/meute.db", busy_timeout_ms=1000, clock=lambda: FIXED
        )


@pytest.fixture
def sandbox(tmp_path: Path) -> Generator[Sandbox]:
    """A fresh sandbox below `tmp_path`; its tmux server is always killed at the end."""
    binary = shutil.which("tmux")  # absolute, so teardown works even if a test empties PATH
    box = Sandbox(root=tmp_path, tmux_socket=f"meute-test-{uuid4().hex}")
    try:
        yield box
    finally:
        if binary is not None:
            kill_socket(binary, box.tmux_socket)


@pytest.fixture
def tmux_server() -> Generator[TestServer]:
    """A throw-away tmux server, always killed at the end of the test."""
    server = TestServer.start()
    try:
        yield server
    finally:
        server.stop()
