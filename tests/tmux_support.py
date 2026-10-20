"""A throw-away tmux server for tests: dedicated socket, empty configuration."""

import os
import shlex
import shutil
import signal
import subprocess
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from meute.tmux.client import Tmux, is_no_server
from meute.tmux.errors import CommandFailed, NotInstalled, TmuxError

_EXIT_GRACE_SECONDS = 5.0


def socket_file(socket: str) -> Path:
    """Return where tmux keeps the socket file of `-L socket`."""
    parent = os.environ.get("TMUX_TMPDIR") or "/tmp"  # noqa: S108 — tmux's own default socket folder
    return Path(parent) / f"tmux-{os.getuid()}" / socket


def kill_socket(
    binary: str, socket: str, path: Path | None = None
) -> subprocess.CompletedProcess[str] | None:
    """Kill the server on `socket`, wait for it to exit; None when there was no socket file.

    The socket file is removed once the server is known gone: killed, or already exited on
    its own (its last pane died); a failed kill keeps it, so a later sweep can retry.
    """
    path = path or socket_file(socket)
    if not path.exists():
        return None
    pid = _server_pid(binary, path)
    killed = subprocess.run(
        [binary, "-S", str(path), "kill-server"], capture_output=True, text=True, check=False
    )
    if pid is not None:
        _wait_for_exit(pid)
    if killed.returncode == 0 or is_no_server(CommandFailed(("kill-server",), killed.stderr)):
        with suppress(OSError):
            path.unlink(missing_ok=True)
    return killed


def _server_pid(binary: str, path: Path) -> int | None:
    shown = subprocess.run(
        [binary, "-S", str(path), "display-message", "-p", "#{pid}"],
        capture_output=True,
        text=True,
        check=False,
    )
    text = shown.stdout.strip()
    return int(text) if shown.returncode == 0 and text.isdigit() else None


def _wait_for_exit(pid: int) -> None:
    """Wait for the tmux server `pid` to exit; kill it if it lingers."""
    deadline = time.monotonic() + _EXIT_GRACE_SECONDS
    while time.monotonic() < deadline:
        if not _alive(pid):
            return
        time.sleep(0.01)
    with suppress(OSError):  # check it is still tmux: the pid may have been reused
        if b"tmux" in Path(f"/proc/{pid}/cmdline").read_bytes():
            os.kill(pid, signal.SIGKILL)


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


RUN_DIR_PREFIX = "meute-tests-"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # another user's process
        return True
    return True


def sweep_stale_run_dirs(binary: str, root: Path) -> None:
    """Clean the `meute-tests-<pid>` folders of `root` whose test run is no longer alive."""
    for folder in root.glob(f"{RUN_DIR_PREFIX}*"):
        pid = folder.name.removeprefix(RUN_DIR_PREFIX)
        if pid.isdigit() and not _alive(int(pid)):
            clean_run_dir(binary, folder)


def clean_run_dir(binary: str, folder: Path) -> None:
    """Kill every tmux server whose socket lies in `folder`, then remove the folder."""
    for sock in folder.glob("tmux-*/*"):
        _ = kill_socket(binary, sock.name, sock)
    shutil.rmtree(folder, ignore_errors=True)


@contextmanager
def attached_client(server: TestServer, *, columns: int, rows: int = 24) -> Generator[str]:
    """Attach a real client to `test` on a terminal of `columns` by `rows`; yield its name.

    `script` gives the client a pseudo-terminal, as tmux needs one to draw popups. The client
    is detached at the end, which ends `script`; it is killed if it lingers.
    """
    attach = shlex.join(
        [server.binary, *server.tmux.base_args()[1:], "attach-session", "-t", "test"]
    )
    environ = {key: value for key, value in os.environ.items() if key != "TMUX"}
    script = shutil.which("script")
    if script is None:
        msg = "script (util-linux) is needed to attach a client"
        raise AssertionError(msg)
    process = subprocess.Popen(
        [script, "-qfc", f"stty cols {columns} rows {rows}; exec {attach}", "/dev/null"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environ,
    )
    try:
        deadline = time.monotonic() + 10
        while not (name := server.tmux.run("list-clients", "-F", "#{client_name}")):
            if time.monotonic() >= deadline:
                msg = "timed out waiting for the client to attach"
                raise AssertionError(msg)
            time.sleep(0.05)
        yield name
    finally:
        with suppress(TmuxError):
            _ = server.tmux.run("detach-client", "-s", "test")
        try:
            _ = process.wait(timeout=_EXIT_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            _ = process.wait()
