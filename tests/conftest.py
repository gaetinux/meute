"""Test configuration: hypothesis profiles chosen by `HYPOTHESIS_PROFILE`."""

import os
import shutil
import subprocess
import sys
from collections.abc import Generator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from hypothesis import settings

from meute.core.db.connection import Database
from meute.tmux.client import Tmux
from support import FIXED
from tmux_support import TestServer, kill_socket

settings.register_profile("dev", max_examples=100)
settings.register_profile("ci", max_examples=1000)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


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
