"""Tests added after mutmut: plan 2 behaviour that earlier tests left unchecked."""

from collections.abc import Callable
from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.repos import _text as repos_text  # pyright: ignore[reportPrivateUsage] — the corrupt-row message is only reachable directly
from meute.core.db.repos import list_repos, sync_repos
from meute.core.db.rows import inserted_id
from meute.core.db.sessions import _text as sessions_text  # pyright: ignore[reportPrivateUsage] — the corrupt-row message is only reachable directly
from meute.core.db.sessions import create_session, find_session, get_session
from meute.core.db.tasks import create_task
from meute.core.errors import NotFound
from meute.core.project import RepoId
from meute.core.reconcile import PaneObservation, reconcile
from meute.core.repo import NewRepo
from meute.core.session import AgentKind, NewSession, Session, SessionId, session_to_json
from meute.core.session_state import Exited, Running, SessionState
from meute.git.discover import discover
from meute.git.kind import RepoKind, detect_kind
from meute.tmux.conf import _tmux_escape  # pyright: ignore[reportPrivateUsage] — the escaping helper is tested directly
from meute.tmux.errors import UnreadableOutput
from meute.tmux.parse import parse_pane_line
from support import FIXED, USER, new_task

FIRST = SessionId("aaaa1111-0000-4000-8000-000000000000")
SECOND = SessionId("aaaa2222-0000-4000-8000-000000000000")


def make(session_id: SessionId, state: SessionState) -> Session:
    return Session(
        id=session_id,
        agent=AgentKind.BASH,
        title="t",
        project_id=None,
        repo_id=None,
        task_id=None,
        cwd=Path("/work"),
        state=state,
        last_activity_at=FIXED,
        created_at=FIXED,
        ended_at=None,
    )


def test_reconcile_goes_on_after_an_ended_session() -> None:
    ended = make(FIRST, Exited(code=0))
    live = make(SECOND, Running())
    result = reconcile([ended, live], [PaneObservation(meute_id=SECOND, dead=True, exit_code=4)])
    assert result.updates == ((SECOND, Exited(code=4)),)


def test_session_json_ended_at_is_null_while_live() -> None:
    assert session_to_json(make(FIRST, Running()))["ended_at"] is None


def test_session_keeps_project_repo_and_task_in_their_own_columns(db: Database) -> None:
    for name in ("filler", "target"):
        project = create_project(db, name)
    for title in ("filler", "target"):
        task = create_task(db, new_task(title, project.id), USER)
    for path in ("/r/one", "/r/two", "/r/three"):
        cursor = db.conn.execute(
            "INSERT INTO repos (path, name, kind, discovered_at) VALUES (?, 'r', NULL, 'x')",
            (path,),
        )
    repo_id = RepoId(inserted_id(cursor))
    new = NewSession(
        id=FIRST,
        agent=AgentKind.BASH,
        title="t",
        cwd=Path("/w"),
        state=Running(),
        project_id=project.id,
        repo_id=repo_id,
        task_id=task.id,
    )
    create_session(db, new)
    got = get_session(db, FIRST)
    assert (got.project_id, got.repo_id, got.task_id) == (2, 3, 2)
    assert (got.project_id, got.repo_id, got.task_id) != (3, 3, 3)


def test_session_without_links_reads_none(db: Database) -> None:
    create_session(
        db, NewSession(id=FIRST, agent=AgentKind.BASH, title="t", cwd=Path("/w"), state=Running())
    )
    got = get_session(db, FIRST)
    assert (got.project_id, got.repo_id, got.task_id) == (None, None, None)


def test_repos_carry_their_database_ids(db: Database) -> None:
    repos = sync_repos(
        db,
        [
            NewRepo(path=Path("/g/a"), name="a", kind=None),
            NewRepo(path=Path("/g/b"), name="b", kind=None),
        ],
    )
    assert [repo.id for repo in repos] == [1, 2]
    assert [repo.id for repo in list_repos(db)] == [1, 2]


@pytest.mark.parametrize("read", [repos_text, sessions_text])
def test_corrupt_text_column_says_what_was_expected(read: Callable[[object], str]) -> None:
    with pytest.raises(ValueError, match=r"^corrupt row: expected text, got 5$"):
        read(5)


def test_unknown_session_names_the_session_and_the_id(db: Database) -> None:
    with pytest.raises(NotFound) as unknown:
        get_session(db, FIRST)
    assert (unknown.value.entity, unknown.value.ident) == ("session", FIRST)
    with pytest.raises(NotFound) as short:
        find_session(db, "abc")
    assert (short.value.entity, short.value.ident) == ("session", "abc")
    with pytest.raises(NotFound) as missing:
        find_session(db, "ffff")
    assert (missing.value.entity, missing.value.ident) == ("session", "ffff")


def test_discovery_goes_on_after_a_root_that_cannot_be_resolved(tmp_path: Path) -> None:
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    good = tmp_path / "good"
    (good / "app" / ".git").mkdir(parents=True)
    assert [item.name for item in discover([loop / "x", good])] == ["app"]


def test_worktree_pointer_file_with_invalid_utf8_is_still_read(tmp_path: Path) -> None:
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "w").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    pointer = f"gitdir: {main}/.git/worktrees/w\n".encode()
    (work / ".git").write_bytes(b"\xff\xfe junk\n" + pointer)
    (found,) = discover([tmp_path])
    assert found.path == main.resolve()
    assert found.worktrees == (work.resolve(),)


def test_fastapi_is_only_looked_for_in_the_first_megabyte(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("#" * (1024 * 1024) + "\nfastapi\n")
    assert detect_kind(tmp_path) is RepoKind.PYTHON


UNREADABLE = r"^unreadable tmux output: "


def test_pane_line_errors_name_the_field_and_the_line() -> None:
    fields = ["%1", "s", "w", "", "", "1", "x", "80"]
    with pytest.raises(UnreadableOutput, match=UNREADABLE + r"exit status in pane line '"):
        parse_pane_line("\t".join(fields))
    fields[6:] = ["", "wide"]
    with pytest.raises(UnreadableOutput, match=UNREADABLE + r"width in pane line '"):
        parse_pane_line("\t".join(fields))
    with pytest.raises(
        UnreadableOutput, match=UNREADABLE + r"expected 8 fields in pane line 'a\\tb'$"
    ):
        parse_pane_line("a\tb")


def test_tmux_escape_only_touches_backslash_quote_and_dollar() -> None:
    assert _tmux_escape('X\\"$x') == 'X\\\\\\"\\$x'
