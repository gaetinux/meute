"""A throw-away tmux server for tests: dedicated socket, empty configuration."""

import os
import shutil
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from meute.tmux.client import Tmux, is_no_server
from meute.tmux.errors import CommandFailed, NotInstalled, TmuxError


def socket_file(socket: str) -> Path:
    """Return where tmux keeps the socket file of `-L socket`."""
    parent = os.environ.get("TMUX_TMPDIR") or "/tmp"  # noqa: S108 — tmux's own default socket folder
    return Path(parent) / f"tmux-{os.getuid()}" / socket


def kill_socket(
    binary: str, socket: str, path: Path | None = None
) -> subprocess.CompletedProcess[str] | None:
    """Kill the server on `socket` and remove its socket file; None when there was no file.

    The file is removed even when the server already exited on its own (its last pane died).
    """
    path = path or socket_file(socket)
    if not path.exists():
        return None
    killed = subprocess.run(
        [binary, "-L", socket, "kill-server"], capture_output=True, text=True, check=False
    )
    with suppress(OSError):
        path.unlink(missing_ok=True)
    return killed


@dataclass(frozen=True, slots=True, kw_only=True)
class TestServer:
    """A tmux server on the socket `meute-test-<uuid>`, started with `-f /dev/null`."""

    __test__ = False  # not a pytest test class

    tmux: Tmux
    binary: str  # absolute path of tmux, so that stop() works even when a test empties PATH
    socket_path: Path | None = None  # known once the server runs, even if a test kills it

    @staticmethod
    def start() -> "TestServer":
        """Start a server holding one detached session called `test`."""
        binary = shutil.which("tmux")
        if binary is None:
            raise NotInstalled
        tmux = Tmux(socket=f"meute-test-{uuid4().hex}", config_file=Path("/dev/null"))
        server = TestServer(tmux=tmux, binary=binary)
        try:
            tmux.run("new-session", "-d", "-s", "test", "-x", "200", "-y", "50")
            path = tmux.run("display-message", "-p", "#{socket_path}")
        except TmuxError:
            server.stop()
            raise
        return TestServer(tmux=tmux, binary=binary, socket_path=Path(path))

    def stop(self) -> None:
        """Kill the server and remove its socket file; an already dead server is fine.

        Raises:
            CommandFailed: kill-server failed for a reason other than a missing server.
        """
        killed = kill_socket(self.binary, self.tmux.socket, self.socket_path)
        if killed is None or killed.returncode == 0:
            return
        error = CommandFailed(("kill-server",), killed.stderr.rstrip())
        if not is_no_server(error):
            raise error
