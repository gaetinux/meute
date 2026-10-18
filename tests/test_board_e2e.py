"""The real dashboard in a real tmux pane: a session appears, Enter shows it."""

from conftest import Sandbox
from meute.core.db.sessions import list_sessions
from support import wait_until

_BOARD_START = 30.0  # Textual's first start can be slow on a loaded machine


def _main_panes(sandbox: Sandbox) -> list[tuple[str, str, str]]:
    """(pane id, @meute_role, @meute_id) of every pane of `meute:main`."""
    output = sandbox.tmux().run(
        "list-panes", "-t", "=meute:main", "-F", "#{pane_id}\t#{@meute_role}\t#{@meute_id}"
    )
    rows: list[tuple[str, str, str]] = []
    for line in output.splitlines():
        pane, role, meute_id = line.split("\t")
        rows.append((pane, role, meute_id))
    return rows


def test_enter_in_the_board_shows_the_session(sandbox: Sandbox) -> None:
    # The server starts here, with the sandbox environment, which its panes inherit.
    assert sandbox.run("layout", "sync").returncode == 0
    (board,) = (pane for pane, role, _ in _main_panes(sandbox) if role == "board")
    folder = sandbox.root / "w"
    folder.mkdir()
    result = sandbox.run("session", "new", "--cwd", str(folder), "--title", "trial")
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (session,) = list_sessions(db)

    def board_text() -> str:
        return sandbox.tmux().run("capture-pane", "-p", "-t", board)

    wait_until(
        "the board to list the session", lambda: "trial" in board_text(), timeout=_BOARD_START
    )
    sandbox.tmux().run("send-keys", "-t", board, "Enter")

    def shown() -> bool:
        panes = _main_panes(sandbox)
        ids = [meute_id for _, _, meute_id in panes]
        return session.id in ids and all(role != "welcome" for _, role, _ in panes)

    wait_until("the session to replace the welcome pane", shown)
