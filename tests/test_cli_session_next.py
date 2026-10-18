"""`meute session next|previous` jump between the sessions that need attention."""

from collections.abc import Callable

from conftest import Sandbox
from meute.core.db.sessions import list_sessions
from meute.core.session import SessionId
from meute.core.session_state import PermissionRequested
from support import wait_until

_START = 30.0


def _new(sandbox: Sandbox, title: str, *, kind: str, script: str = "permission") -> SessionId:
    folder = sandbox.root / "w"
    folder.mkdir(exist_ok=True)
    env = {"MEUTE_FAKE_CLAUDE_SCRIPT": script}
    result = sandbox.run(
        "session", "new", "--kind", kind, "--cwd", str(folder), "--title", title, env=env
    )
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (session,) = (s for s in list_sessions(db) if s.title == title)
    return session.id


def _asking(sandbox: Sandbox, *ids: SessionId) -> Callable[[], bool]:
    def ready() -> bool:
        _ = sandbox.run("session", "list")  # reconciles the states
        with sandbox.db() as db:
            states = {s.id: s.state for s in list_sessions(db)}
        return all(isinstance(states[i], PermissionRequested) for i in ids)

    return ready


def _displayed(sandbox: Sandbox) -> str:
    out = sandbox.tmux().run("list-panes", "-t", "=meute:main", "-F", "#{@meute_id}")
    return next((line for line in out.splitlines() if line), "")


def _jump(sandbox: Sandbox, direction: str) -> str:
    result = sandbox.run("session", direction)
    assert (result.returncode, result.stderr) == (0, "")
    return _displayed(sandbox)


def _three(sandbox: Sandbox) -> tuple[SessionId, SessionId, SessionId]:
    assert sandbox.run("layout", "sync").returncode == 0
    first = _new(sandbox, "one", kind="claude")
    quiet = _new(sandbox, "quiet", kind="bash")
    second = _new(sandbox, "two", kind="claude")
    wait_until("both to ask", _asking(sandbox, first, second), timeout=_START)
    return first, quiet, second


def test_next_loops_over_the_sessions_needing_attention(sandbox: Sandbox) -> None:
    first, quiet, second = _three(sandbox)
    one = _jump(sandbox, "next")
    two = _jump(sandbox, "next")
    assert {one, two} == {first, second}
    assert _jump(sandbox, "next") == one
    assert quiet not in {one, two}


def test_previous_goes_the_other_way(sandbox: Sandbox) -> None:
    _three(sandbox)
    one = _jump(sandbox, "next")
    two = _jump(sandbox, "next")
    assert _jump(sandbox, "previous") == one
    assert _jump(sandbox, "previous") == two


def test_jump_updates_the_status_line(sandbox: Sandbox) -> None:
    _three(sandbox)
    _ = _jump(sandbox, "next")
    status = sandbox.tmux().run("show-options", "-gv", "@meute_status")
    assert status.startswith("▶ ")
    assert "2" in status


def test_nothing_needs_attention_changes_nothing(sandbox: Sandbox) -> None:
    assert sandbox.run("layout", "sync").returncode == 0
    _ = _new(sandbox, "quiet", kind="bash")
    before = _displayed(sandbox)
    assert _jump(sandbox, "next") == before
    assert _jump(sandbox, "previous") == before
