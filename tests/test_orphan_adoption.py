"""`adoption`: what an orphan pane becomes in the database, or why it cannot."""

from datetime import UTC, datetime
from pathlib import Path

from meute.core.orphans import (
    ORPHAN_FOOTER,
    Orphan,
    adoption,
    closing_text,
    confirm_close_text,
)
from meute.core.project import RepoId
from meute.core.repo import Repo
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running, Unknown

_ID = "11111111-1111-4111-8111-111111111111"
_AT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


def _orphan(**fields: object) -> Orphan:
    base = {"meute_id": _ID, "pane_id": "%1", "command": "claude", "cwd": "/srv/x", "dead": False}
    return Orphan(**(base | fields))  # pyright: ignore[reportArgumentType] — test helper


def _repo(repo_id: int, path: str) -> Repo:
    return Repo(id=RepoId(repo_id), path=Path(path), name="r", kind=None, discovered_at=_AT)


def test_a_claude_orphan_is_adopted_with_an_unknown_state() -> None:
    assert adoption(_orphan(), ()) == NewSession(
        id=SessionId(_ID), agent=AgentKind.CLAUDE, title="x", cwd=Path("/srv/x"), state=Unknown()
    )


def test_a_bash_orphan_is_adopted_as_running() -> None:
    found = adoption(_orphan(command="bash"), ())
    assert isinstance(found, NewSession)
    assert (found.agent, found.state) == (AgentKind.BASH, Running())


def test_the_longest_repository_containing_the_folder_wins() -> None:
    repos = (_repo(1, "/srv"), _repo(2, "/srv/x"), _repo(3, "/srv/xy"), _repo(4, "/other"))
    found = adoption(_orphan(cwd="/srv/x/sub"), repos)
    assert isinstance(found, NewSession)
    assert found.repo_id == RepoId(2)


def test_no_repository_contains_the_folder() -> None:
    found = adoption(_orphan(), (_repo(1, "/other"),))
    assert isinstance(found, NewSession)
    assert found.repo_id is None


def test_an_empty_folder_is_titled_orphan() -> None:
    found = adoption(_orphan(cwd="/"), ())
    assert isinstance(found, NewSession)
    assert found.title == "orphan"


def test_an_identifier_that_is_not_a_meute_id_is_refused() -> None:
    for hostile in ("x;y", "x" * 37, "a\x1b[2J", "%7", ""):
        assert adoption(_orphan(meute_id=hostile), ()) == "not a meute id: only x closes it"


def test_a_dead_pane_is_refused() -> None:
    assert adoption(_orphan(dead=True), ()) == "dead pane: only x closes it"


def test_the_texts_show_the_command_through_printable() -> None:
    assert ORPHAN_FOOTER == "Enter show · a adopt · x close"
    assert (
        confirm_close_text("claude\x1b[2J")
        == 'Close orphan pane "claude�[2J"? y: yes · any other key: no'
    )
    assert closing_text("a\nb") == 'Closing "a�b"…'
