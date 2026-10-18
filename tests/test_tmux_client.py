from pathlib import Path

import pytest

from meute.tmux.client import Tmux, is_no_server
from meute.tmux.errors import CommandFailed, UnreadableOutput
from tmux_support import TestServer


def test_start_run_and_kill(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    assert tmux.is_running()
    assert tmux.has_session("test")
    assert not tmux.has_session("tes")
    assert tmux.run("display-message", "-p", "hello") == "hello"
    tmux.kill_server()
    assert not tmux.is_running()


def test_failed_command_reports_stderr(tmux_server: TestServer) -> None:
    with pytest.raises(CommandFailed) as raised:
        tmux_server.tmux.run("kill-pane", "-t", "%999")
    assert raised.value.stderr != ""
    assert raised.value.args == ("kill-pane", "-t", "%999")
    assert str(raised.value).startswith("tmux kill-pane -t %999 failed: ")


def test_never_started_socket_is_not_running() -> None:
    tmux = Tmux(socket="meute-test-never-started")
    assert not tmux.is_running()
    assert not tmux.has_session("test")


def test_base_args() -> None:
    assert Tmux(socket="s").base_args() == ["tmux", "-L", "s"]
    assert Tmux(socket="s", config_file=Path("/x.conf")).base_args() == [
        "tmux",
        "-L",
        "s",
        "-f",
        "/x.conf",
    ]


def test_is_no_server() -> None:
    assert is_no_server(CommandFailed(["ls"], "no server running on /tmp/x"))
    assert is_no_server(CommandFailed(["ls"], "error connecting to /tmp/x (No such file)"))
    assert not is_no_server(CommandFailed(["ls"], "boom"))


def test_unreadable_output_message() -> None:
    assert str(UnreadableOutput("x")) == "unreadable tmux output: x"


def test_stop_removes_the_socket_file() -> None:
    server = TestServer.start()
    socket = Path(server.tmux.run("display-message", "-p", "#{socket_path}"))
    assert socket.exists()
    server.stop()
    assert not socket.exists()


def test_stop_works_when_path_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    server = TestServer.start()
    socket = Path(server.tmux.run("display-message", "-p", "#{socket_path}"))
    with monkeypatch.context() as patch:
        patch.setenv("PATH", "")
        server.stop()
    with pytest.raises(CommandFailed) as raised:
        server.tmux.run("ls")
    assert is_no_server(raised.value)
    assert not socket.exists()
