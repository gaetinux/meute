"""End-to-end tests of `meute session show` and `meute session stop`."""

import re
import stat
from pathlib import Path

from conftest import Sandbox
from meute.core.db.sessions import list_sessions
from meute.core.session import SessionId
from meute.core.session_state import Exited, Running
from meute.tmux.client import Tmux
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.layout import ensure_layout
from support import wait_until

_SLEEP = ("sh", "-c", "sleep 3600")
_SPEC = LayoutSpec(
    board_width=60,
    narrow_threshold=100,
    board_command=_SLEEP,
    welcome_command=_SLEEP,
    sync_command=("true",),
    keys=Keys(focus_board="M-p", focus_main="M-o"),
)


def _layout(sandbox: Sandbox) -> Tmux:
    # The throw-away server must not read the user's tmux.conf.
    tmux = Tmux(socket=sandbox.tmux_socket, config_file=Path("/dev/null"))
    ensure_layout(tmux, _SPEC)
    return tmux


def _new(sandbox: Sandbox, title: str, env: dict[str, str] | None = None) -> SessionId:
    folder = sandbox.root / "w"
    folder.mkdir(exist_ok=True)
    result = sandbox.run(
        "session", "new", "--kind", "bash", "--cwd", str(folder), "--title", title, env=env
    )
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (session,) = (s for s in list_sessions(db) if s.title == title)
    return session.id


def _panes(sandbox: Sandbox) -> list[tuple[str, str, str, str]]:
    """(pane id, session, window, meute id or role) of every pane."""
    fmt = "#{pane_id} #{session_name} #{window_name} #{@meute_id}#{@meute_role}"
    output = sandbox.tmux().run("list-panes", "-a", "-F", fmt)
    rows: list[tuple[str, str, str, str]] = []
    for line in output.splitlines():
        pane, session, window, tag = line.split(" ")
        rows.append((pane, session, window, tag))
    return rows


def _main_window(sandbox: Sandbox) -> list[tuple[str, str]]:
    return [(p[0], p[3]) for p in _panes(sandbox) if p[1] == "meute"]


def _pane_of(sandbox: Sandbox, session_id: str) -> tuple[str, str]:
    (found,) = ((p[0], p[1]) for p in _panes(sandbox) if p[3] == session_id)
    return found


def test_show_swaps_session_into_main_and_drops_welcome(sandbox: Sandbox) -> None:
    _layout(sandbox)
    session_id = _new(sandbox, "alpha")
    result = sandbox.run("session", "show", session_id[:8])
    assert (result.returncode, result.stderr) == (0, "")
    roles = [role for _, role in _main_window(sandbox)]
    assert session_id in roles
    assert "welcome" not in roles
    assert sandbox.tmux().run("show-options", "-gv", "@meute_status") == "▶ alpha"


def test_show_second_session_sends_first_back_to_bg(sandbox: Sandbox) -> None:
    _layout(sandbox)
    first = _new(sandbox, "alpha")
    second = _new(sandbox, "beta")
    assert sandbox.run("session", "show", first[:8]).returncode == 0
    first_pane, _ = _pane_of(sandbox, first)
    assert sandbox.run("session", "show", second[:8]).returncode == 0
    assert _pane_of(sandbox, first) == (first_pane, "meute-bg")
    assert _pane_of(sandbox, second)[1] == "meute"


def test_show_displayed_session_only_selects_it(sandbox: Sandbox) -> None:
    _layout(sandbox)
    session_id = _new(sandbox, "alpha")
    assert sandbox.run("session", "show", session_id[:8]).returncode == 0
    before = sorted(_panes(sandbox))
    result = sandbox.run("session", "show", session_id[:8])
    assert (result.returncode, result.stderr) == (0, "")
    assert sorted(_panes(sandbox)) == before


def test_show_without_layout_fails_with_hint(sandbox: Sandbox) -> None:
    session_id = _new(sandbox, "alpha")
    result = sandbox.run("session", "show", session_id[:8])
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == 'meute: meute is not open: run "meute" first\n'


def test_show_by_prefix_and_ambiguous_prefix(sandbox: Sandbox) -> None:
    _layout(sandbox)
    session_id = _new(sandbox, "alpha")
    assert sandbox.run("session", "show", session_id[:4]).returncode == 0
    with sandbox.db() as db:
        db.conn.execute("UPDATE sessions SET id = ? WHERE id = ?", ("x" * 36, session_id))
    other = _new(sandbox, "beta")
    with sandbox.db() as db:
        db.conn.execute("UPDATE sessions SET id = ? WHERE id = ?", ("x" * 35 + "y", other))
    result = sandbox.run("session", "show", "xxxx")
    assert (result.returncode, result.stderr) == (1, "meute: ambiguous session id: xxxx\n")


def test_show_unreachable_session_fails(sandbox: Sandbox) -> None:
    _layout(sandbox)
    session_id = _new(sandbox, "alpha")
    pane, _ = _pane_of(sandbox, session_id)
    sandbox.tmux().run("kill-pane", "-t", pane)
    result = sandbox.run("session", "show", session_id[:8])
    assert (result.returncode, result.stderr) == (1, "meute: session unreachable: alpha\n")


def _dying_shell(sandbox: Sandbox) -> dict[str, str]:
    script = sandbox.root / "shell.sh"
    script.write_text("#!/bin/sh\nexec sleep 3600\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return {"SHELL": str(script)}


def test_stop_with_yes_kills_and_marks_exited(sandbox: Sandbox) -> None:
    _layout(sandbox)
    session_id = _new(sandbox, "alpha", _dying_shell(sandbox))
    result = sandbox.run("session", "stop", session_id[:8], "--yes")
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == f"Stopped: {session_id[:8]} alpha\n"
    with sandbox.db() as db:
        (session,) = list_sessions(db, include_ended=True)
    assert isinstance(session.state, Exited)
    assert all(p[3] != session_id for p in _panes(sandbox))


def test_stop_displayed_session_restores_welcome(sandbox: Sandbox) -> None:
    _layout(sandbox)
    session_id = _new(sandbox, "alpha", _dying_shell(sandbox))
    assert sandbox.run("session", "show", session_id[:8]).returncode == 0
    result = sandbox.run("session", "stop", session_id[:8], "--yes")
    assert result.returncode == 0, result.stderr
    roles = [role for _, role in _main_window(sandbox)]
    assert sorted(roles) == ["board", "welcome"]
    widths = sandbox.tmux().run(
        "list-panes", "-t", "=meute:main", "-F", "#{@meute_role} #{pane_width}"
    )
    assert "board 72" in widths.splitlines()


def test_stop_without_confirmation_cancels(sandbox: Sandbox) -> None:
    _layout(sandbox)
    session_id = _new(sandbox, "alpha")
    result = sandbox.run("session", "stop", session_id[:8], stdin="n\n")
    assert (result.returncode, result.stdout) == (0, "Cancelled.\n")
    assert result.stderr == 'Stop session "alpha"? [y/N] '
    with sandbox.db() as db:
        (session,) = list_sessions(db)
    assert session.state == Running()
    assert any(p[3] == session_id for p in _panes(sandbox))


def test_stop_confirmation_accepts_yes_in_any_case(sandbox: Sandbox) -> None:
    _layout(sandbox)
    session_id = _new(sandbox, "alpha", _dying_shell(sandbox))
    result = sandbox.run("session", "stop", session_id[:8], stdin="  YES \n")
    assert (result.returncode, result.stdout) == (0, f"Stopped: {session_id[:8]} alpha\n")
    wait_until("the pane to be gone", lambda: all(p[3] != session_id for p in _panes(sandbox)))


def test_stop_unknown_session_fails(sandbox: Sandbox) -> None:
    result = sandbox.run("session", "stop", "deadbeef", "--yes")
    assert (result.returncode, result.stdout) == (4, "")
    assert re.fullmatch(r"meute: .*deadbeef.*\n", result.stderr)
