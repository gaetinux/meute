"""A throw-away tmux server for tests: dedicated socket, empty configuration."""

import shutil
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from meute.tmux.client import Tmux
from meute.tmux.errors import NotInstalled, TmuxError


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

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.binary, "-L", self.tmux.socket, *args],
            capture_output=True,
            text=True,
            check=False,
        )

    def stop(self) -> None:
        """Kill the server and remove its socket file; an already dead server is fine."""
        self._run("kill-server")
        if self.socket_path is not None:
            with suppress(OSError):
                self.socket_path.unlink(missing_ok=True)
