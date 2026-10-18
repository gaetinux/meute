"""End-to-end tests of `meute session list` on a throw-away tmux server."""

import re
from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from conftest import Sandbox
from meute.core.db.sessions import create_session, list_sessions
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from support import load_json, wait_until


def _new(sandbox: Sandbox, name: str = "w") -> str:
    """Start a Bash session in a fresh folder and return its full identifier."""
    folder = (sandbox.root / name).resolve()
    folder.mkdir()
    assert sandbox.run("session", "new", "--cwd", str(folder)).returncode == 0
    with sandbox.db() as db:
        return next(s.id for s in list_sessions(db) if s.cwd == folder)


def _pane_of(sandbox: Sandbox, session_id: str) -> str:
    lines = sandbox.tmux().run("list-panes", "-a", "-F", "#{pane_id} #{@meute_id}").splitlines()
    return next(line.split()[0] for line in lines if line.endswith(session_id))


def test_exited_shell_is_reported_with_its_code(sandbox: Sandbox) -> None:
    session_id = _new(sandbox)
    pane = _pane_of(sandbox, session_id)
    tmux = sandbox.tmux()
    tmux.run("send-keys", "-t", pane, "exit 7", "Enter")
    wait_until(
        "the pane to die with its status",
        lambda: (
            tmux.run("display-message", "-p", "-t", pane, "#{pane_dead}:#{pane_dead_status}")
            == "1:7"
        ),
    )
    result = sandbox.run("session", "list")
    assert result.returncode == 0, result.stderr
    assert re.fullmatch(rf"{session_id[:8]}  w  exited \(7\)  .*/w\n", result.stdout), result.stdout


def test_killed_pane_is_unreachable(sandbox: Sandbox) -> None:
    session_id = _new(sandbox)
    other = _new(sandbox, "keep")
    sandbox.tmux().run("kill-pane", "-t", _pane_of(sandbox, session_id))
    result = sandbox.run("session", "list", "--all")
    lines = result.stdout.splitlines()
    # The clock is frozen, so the order of the rows follows the random identifiers.
    assert sorted(line.split("  ")[:3] for line in lines) == sorted(
        [[session_id[:8], "w", "unreachable"], [other[:8], "keep", "running"]]
    )
    assert sandbox.run("session", "list").stdout.count("\n") == 1


def test_list_without_server_marks_sessions_unreachable(
    sandbox: Sandbox, snapshot: SnapshotAssertion
) -> None:
    assert sandbox.run("config", "path").returncode == 0  # creates the database
    with sandbox.db() as db:
        for number, name in enumerate(("build", "tests"), start=1):
            create_session(
                db,
                NewSession(
                    id=SessionId(f"{number}" * 8 + "-1111-4111-8111-" + f"{number}" * 12),
                    agent=AgentKind.BASH,
                    title=name,
                    cwd=Path("/srv") / name,
                    state=Running(),
                ),
            )
    assert sandbox.run("session", "list").stdout == ""
    result = sandbox.run("session", "list", "--all")
    assert result.stdout == snapshot
    assert not sandbox.tmux().is_running()


def test_orphan_pane_is_listed(sandbox: Sandbox) -> None:
    sandbox.tmux().run("new-session", "-d", "-s", "meute-bg", "--", "sleep", "30")
    sandbox.tmux().run("set-option", "-p", "-t", "meute-bg:", "@meute_id", "ghost-id")
    result = sandbox.run("session", "list")
    assert (result.returncode, result.stdout) == (0, "orphan: ghost-id\n")


def test_list_json_shape(sandbox: Sandbox) -> None:
    session_id = _new(sandbox)
    result = sandbox.run("session", "list", "--json")
    payload = load_json(result.stdout)
    assert isinstance(payload, dict)
    assert set(payload) == {"sessions", "orphans"}
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    first = sessions[0]
    assert isinstance(first, dict)
    assert (first["id"], first["state"], payload["orphans"]) == (
        session_id,
        {"kind": "running"},
        [],
    )


def test_all_includes_ended_sessions(sandbox: Sandbox) -> None:
    session_id = _new(sandbox)
    sandbox.tmux().run("kill-pane", "-t", _pane_of(sandbox, session_id))
    assert sandbox.run("session", "list").stdout == ""
    assert sandbox.run("session", "list", "--all").stdout.startswith(session_id[:8])
