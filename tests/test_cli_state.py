"""`meute state save|list|open|rm`, end to end on a throw-away home and tmux server."""

from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from conftest import Sandbox
from meute.core.db.saved_states import get_state, list_states, save_state
from meute.core.saved_state import SavedSession
from meute.core.session import AgentKind, SessionId
from support import load_json

_IDS = {
    "one": SessionId("aaaa1111-0000-4000-8000-000000000000"),
    "a": SessionId("bbbb2222-0000-4000-8000-000000000000"),
    "b": SessionId("cccc3333-0000-4000-8000-000000000000"),
}


def _entry(title: str, cwd: Path) -> SavedSession:
    return SavedSession(
        session_id=_IDS[title],
        agent=AgentKind.BASH,
        cwd=cwd,
        native_id=None,
        title=title,
        task_id=None,
        repo_id=None,
        displayed=False,
    )


def _seed(sandbox: Sandbox) -> None:
    """Three states: `last` with one session, `review` with two, `empty` with none."""
    assert sandbox.run("config", "path").returncode == 0  # creates the database
    home = sandbox.root / "home"
    home.mkdir(exist_ok=True)
    with sandbox.db() as db:
        _ = save_state(db, "last", [_entry("one", home)])
        _ = save_state(db, "review", [_entry("a", home), _entry("b", home)])
        _ = save_state(db, "empty", [])


def test_save_without_a_session_stamps_the_local_time(sandbox: Sandbox) -> None:
    result = sandbox.run("state", "save")
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "Saved: 2026-10-14 10:30 (0 sessions)\n"
    with sandbox.db() as db:
        assert [state.name for state in list_states(db)] == ["2026-10-14 10:30"]


def test_save_under_a_name_captures_the_live_sessions(sandbox: Sandbox) -> None:
    folder = sandbox.root / "w"
    folder.mkdir()
    for title in ("one", "two"):
        new = sandbox.run(
            "session", "new", "--kind", "bash", "--cwd", str(folder), "--title", title
        )
        assert new.returncode == 0, new.stderr
    result = sandbox.run("state", "save", "  review  ")
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "Saved: review (2 sessions)\n"
    with sandbox.db() as db:
        assert sorted(s.title for s in get_state(db, "review").sessions) == ["one", "two"]
    assert sandbox.run("state", "save", "review").stdout == "Saved: review (2 sessions)\n"


def test_save_counts_one_session_in_the_singular(sandbox: Sandbox) -> None:
    folder = sandbox.root / "w"
    folder.mkdir()
    assert sandbox.run("session", "new", "--kind", "bash", "--cwd", str(folder)).returncode == 0
    assert sandbox.run("state", "save", "solo").stdout == "Saved: solo (1 session)\n"


def test_save_prints_a_clean_name(sandbox: Sandbox) -> None:
    result = sandbox.run("state", "save", "a\x1b[2Jb")
    assert result.returncode == 0, result.stderr
    assert "\x1b" not in result.stdout
    assert result.stdout.startswith("Saved: a")


def test_save_refuses_a_bad_name(sandbox: Sandbox) -> None:
    empty = sandbox.run("state", "save", "  ")
    assert (empty.returncode, empty.stderr) == (1, "meute: state name is empty\n")
    last = sandbox.run("state", "save", "last")
    assert (last.returncode, last.stderr) == (1, "meute: last is kept by the board\n")


def test_list_text(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    _seed(sandbox)
    result = sandbox.run("state", "list")
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == snapshot


def test_list_json(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    _seed(sandbox)
    result = sandbox.run("state", "list", "--json")
    assert (result.returncode, result.stderr) == (0, "")
    assert load_json(result.stdout) == snapshot


def test_list_without_a_state_prints_nothing(sandbox: Sandbox) -> None:
    result = sandbox.run("state", "list")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert load_json(sandbox.run("state", "list", "--json").stdout) == {"states": []}


def test_open_an_empty_state_reports_zero(sandbox: Sandbox) -> None:
    _seed(sandbox)
    result = sandbox.run("state", "open", "empty")
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "reopened 0 · skipped 0\n"


def test_open_reports_the_skipped_sessions(sandbox: Sandbox) -> None:
    _seed(sandbox)
    assert sandbox.run("layout", "sync").returncode == 0
    result = sandbox.run("state", "open", "review")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "reopened 2 · skipped 0"
    again = sandbox.run("state", "open", "review")
    assert again.stdout.splitlines()[0] == "reopened 0 · skipped 2"
    assert again.stdout.splitlines()[1] == "  a: already running"


def test_open_an_unknown_name_exits_1(sandbox: Sandbox) -> None:
    result = sandbox.run("state", "open", "nope")
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == "meute: no saved state named nope\n"


def test_open_takes_the_name_as_typed(sandbox: Sandbox) -> None:
    _seed(sandbox)
    result = sandbox.run("state", "open", "last")
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout.startswith("reopened")


def test_rm_asks_then_removes(sandbox: Sandbox) -> None:
    _seed(sandbox)
    result = sandbox.run("state", "rm", "review", stdin="y\n")
    assert (result.returncode, result.stdout) == (0, "Removed: review\n")
    assert result.stderr == 'Remove saved state "review"? [y/N]'
    with sandbox.db() as db:
        assert "review" not in [s.name for s in list_states(db)]


def test_rm_without_confirmation_removes_nothing(sandbox: Sandbox) -> None:
    _seed(sandbox)
    result = sandbox.run("state", "rm", "review", stdin="n\n")
    assert (result.returncode, result.stdout) == (0, "Cancelled.\n")
    with sandbox.db() as db:
        assert "review" in [s.name for s in list_states(db)]


def test_rm_yes_skips_the_question_and_can_remove_last(sandbox: Sandbox) -> None:
    _seed(sandbox)
    result = sandbox.run("state", "rm", "last", "--yes")
    assert (result.returncode, result.stdout, result.stderr) == (0, "Removed: last\n", "")


def test_rm_an_unknown_name_exits_1(sandbox: Sandbox) -> None:
    result = sandbox.run("state", "rm", "nope", "--yes")
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == "meute: no saved state named nope\n"
