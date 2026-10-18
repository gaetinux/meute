"""A throw-away tmux server for tests: dedicated socket, empty configuration."""

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from meute.tmux.client import Tmux
from meute.tmux.errors import TmuxError


@dataclass(frozen=True, slots=True, kw_only=True)
class TestServer:
    """A tmux server on the socket `meute-test-<uuid>`, started with `-f /dev/null`."""

    __test__ = False  # not a pytest test class

    tmux: Tmux

    @staticmethod
    def start() -> "TestServer":
        """Start a server holding one detached session called `test`."""
        tmux = Tmux(socket=f"meute-test-{uuid4().hex}", config_file=Path("/dev/null"))
        server = TestServer(tmux=tmux)
        try:
            tmux.run("new-session", "-d", "-s", "test", "-x", "200", "-y", "50")
        except TmuxError:
            server.stop()
            raise
        return server

    def stop(self) -> None:
        """Kill the server; an already dead server is fine."""
        with suppress(TmuxError):
            self.tmux.kill_server()
