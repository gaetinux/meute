"""End-to-end Claude sessions: a fake `claude` replays real hooks through meute settings."""

from collections.abc import Callable

from conftest import Sandbox
from meute.core.db.claude_sessions import get_claude_details
from meute.core.db.samples import latest_metrics
from meute.core.db.sessions import list_sessions
from meute.core.session import Session
from support import wait_until

_BOARD_START = 30.0  # Textual's first start can be slow on a loaded machine


def _new(sandbox: Sandbox, script: str, title: str = "trial") -> Session:
    """Start a Claude session whose fake `claude` replays `script`."""
    folder = sandbox.root / "w"
    folder.mkdir(exist_ok=True)
    env = {"MEUTE_FAKE_CLAUDE_SCRIPT": script}
    result = sandbox.run("session", "new", "--cwd", str(folder), "--title", title, env=env)
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (session,) = list_sessions(db)
    return session


def _listed(sandbox: Sandbox, *needles: str) -> Callable[[], bool]:
    return lambda: all(needle in sandbox.run("session", "list").stdout for needle in needles)


def test_claude_session_reaches_permission_requested(sandbox: Sandbox) -> None:
    _new(sandbox, "permission")
    wait_until("the permission request", _listed(sandbox, "permission", "[manual]"), timeout=30)


def test_finished_turn_waits_for_reply(sandbox: Sandbox) -> None:
    session = _new(sandbox, "done")
    wait_until("the finished turn", _listed(sandbox, "waiting for your reply"), timeout=30)
    with sandbox.db() as db:
        message = get_claude_details(db, session.id).last_message
    assert message is not None
    assert message.startswith("La commande a affiché")


def test_session_end_then_exit_is_exited(sandbox: Sandbox) -> None:
    _new(sandbox, "exit")
    wait_until("the session to be exited", _listed(sandbox, "exited"), timeout=30)


def test_statusline_samples_are_recorded(sandbox: Sandbox) -> None:
    session = _new(sandbox, "done")

    def recorded() -> bool:
        with sandbox.db() as db:
            return latest_metrics(db, session.id) is not None

    wait_until("a metric sample", recorded, timeout=30)
    with sandbox.db() as db:
        metrics = latest_metrics(db, session.id)
    assert metrics is not None
    assert metrics.model_name == "Opus 5.5"


def test_dashboard_shows_claude_states(sandbox: Sandbox) -> None:
    assert sandbox.run("layout", "sync").returncode == 0
    panes = sandbox.tmux().run(
        "list-panes", "-t", "=meute:main", "-F", "#{pane_id}\t#{@meute_role}"
    )
    (board,) = (line.split("\t")[0] for line in panes.splitlines() if line.endswith("\tboard"))
    _new(sandbox, "permission", title="claudy")

    def row() -> bool:
        text = sandbox.tmux().run("capture-pane", "-p", "-t", board)
        return any("claudy" in line and "permission" in line for line in text.splitlines())

    wait_until("the board row to show permission", row, timeout=_BOARD_START)
