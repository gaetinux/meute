"""Clients of the throw-away tmux server: an attached terminal and short-lived `-p` jobs."""

import time
from pathlib import Path

import pytest

from tmux_support import TestServer, attached_client, run_format_job


def test_attached_client_needs_no_term_from_the_caller(
    tmux_server: TestServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # CI runners set no TERM; tmux refuses such a terminal ("terminal does not support clear").
    monkeypatch.delenv("TERM", raising=False)
    with attached_client(tmux_server, columns=80) as client:
        assert client


def test_attached_client_fails_fast_with_the_client_error(tmux_server: TestServer) -> None:
    tmux_server.tmux.run("new-session", "-d", "-s", "other")
    tmux_server.tmux.run("kill-session", "-t", "test")
    start = time.monotonic()
    with (
        pytest.raises(AssertionError, match="can't find session"),
        attached_client(tmux_server, columns=80),
    ):
        pass
    assert time.monotonic() - start < 5


def test_tmux_kills_the_job_of_a_print_client_when_it_exits(
    tmux_server: TestServer, tmp_path: Path
) -> None:
    # Why run_format_job exists: the job dies with its `-p` client (tmux 3.6 often kills it
    # before even a bare `touch` ran).
    done = tmp_path / "done"
    tmux_server.tmux.run("display-message", "-p", f"#(sleep 0.2; touch {done})")
    time.sleep(0.5)
    assert not done.exists()


def test_a_format_job_outlives_its_short_lived_client(
    tmux_server: TestServer, tmp_path: Path
) -> None:
    done = tmp_path / "done"
    run_format_job(tmux_server.tmux, f"sleep 0.2; touch {done}", done)
    assert done.exists()
