"""Launching Claude on a task: its repository, the session linked to it, the text pasted unsent."""

import time
from collections.abc import Generator
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import FAKE_CLAUDE_DIR
from meute.cli.context import BUSY_TIMEOUT_MS, CliContext
from meute.cli.task_launch import READY_TIMEOUT_SECONDS, launch_on_task, task_launch_folder
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.context import work_on_task_text
from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.repos import sync_repos
from meute.core.db.sessions import list_sessions
from meute.core.db.task_notes import add_note
from meute.core.db.tasks import create_task, get_task
from meute.core.errors import InvalidInput, PromptNotPasted
from meute.core.paths import Paths
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.repo import NewRepo, Repo
from meute.core.status import Todo
from meute.core.task import Task, TaskId
from meute.tmux.layout import ensure_layout
from meute.tmux.names import MAIN_SESSION
from meute.tmux.panes import list_panes
from support import FIXED, USER, board_repo, load_json, make_task, new_task, wait_until
from test_board_backend import _SPEC, env  # noqa: F401 — fixture reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixture reused

_START, _END = "\x1b[200~", "\x1b[201~"
_SETTLE_SECONDS = 0.5  # long enough for a stray Enter after the paste to show up


# --- task_launch_folder ---------------------------------------------------------------------


def _repos(*repos: Repo) -> dict[RepoId, Repo]:
    return {repo.id: repo for repo in repos}


def test_the_task_repository_comes_first() -> None:
    own, other = board_repo(1, "own", None), board_repo(2, "other", None)
    task = replace(make_task(3), repo_id=own.id)
    assert task_launch_folder(task, _repos(own, other), [other.id]) == own.path


def test_else_the_first_repository_of_its_project() -> None:
    first, second = board_repo(1, "first", None), board_repo(2, "second", None)
    task = replace(make_task(3), project=ProjectRef(id=ProjectId(1), name="meute"))
    assert task_launch_folder(task, _repos(first, second), [second.id, first.id]) == second.path


def test_no_repository_is_refused() -> None:
    message = r"^#3 has no repository: set one on the task or its project$"
    with pytest.raises(InvalidInput, match=message):
        task_launch_folder(make_task(3), _repos(board_repo(1, "a", None)), [])


def test_else_the_repository_named_like_its_project() -> None:
    other, named = board_repo(1, "other", None), board_repo(2, "Meute", None)
    task = replace(make_task(3), project=ProjectRef(id=ProjectId(1), name=" meute "))
    assert task_launch_folder(task, _repos(other, named), []) == named.path


def test_a_linked_repository_beats_the_one_named_like_the_project() -> None:
    linked, named = board_repo(1, "linked", None), board_repo(2, "meute", None)
    task = replace(make_task(3), project=ProjectRef(id=ProjectId(1), name="meute"))
    assert task_launch_folder(task, _repos(linked, named), [linked.id]) == linked.path


def test_no_repository_named_like_the_project_is_refused() -> None:
    task = replace(make_task(3), project=ProjectRef(id=ProjectId(1), name="meute"))
    with pytest.raises(InvalidInput, match=r"^#3 has no repository: "):
        task_launch_folder(task, _repos(board_repo(1, "other", None)), [])


def test_prompt_not_pasted_names_the_timeout_it_was_given() -> None:
    error = PromptNotPasted(TaskId(3), timeout_seconds=2.5)
    assert str(error) == "#3: prompt not pasted (Claude not ready after 2.5 s)"
    assert str(PromptNotPasted(TaskId(3), timeout_seconds=READY_TIMEOUT_SECONDS)).endswith(
        "(Claude not ready after 10 s)"
    )


# --- launch_on_task, with the fake claude -----------------------------------------------------


@pytest.fixture
def ctx(tmp_path: Path) -> Generator[CliContext]:
    roots = {name: str(tmp_path / "xdg") for name in ("XDG_DATA_HOME", "XDG_STATE_HOME")}
    paths = Paths.from_env(roots, home=tmp_path)
    paths.ensure_dirs()
    with Database.open(paths.db_file, busy_timeout_ms=BUSY_TIMEOUT_MS, clock=lambda: FIXED) as db:
        yield CliContext(
            db=db,
            now=FIXED,
            actor=Actor(author=Author.USER, channel=Channel.CLI),
            config=Config(),
            paths=paths,
        )


_ENVIRON = {"PATH": str(FAKE_CLAUDE_DIR)}  # the fake claude only


def _fake_claude(tmux_env: TmuxEnv, tmp_path: Path, script: str) -> Path:
    """Make the panes run the fake `claude` in `script` mode, its hooks writing to the test base."""
    recorded = tmp_path / "input"
    variables = {
        "XDG_DATA_HOME": str(tmp_path / "xdg"),
        "XDG_STATE_HOME": str(tmp_path / "xdg"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "MEUTE_TMUX_SOCKET": tmux_env.tmux.socket,
        "MEUTE_FAKE_CLAUDE_SCRIPT": script,
        "MEUTE_FAKE_CLAUDE_INPUT": str(recorded),
        "MEUTE_FAKE_CLAUDE_ARGS": str(tmp_path / "args.json"),
    }
    for name, value in variables.items():
        _ = tmux_env.tmux.run("set-environment", "-g", name, value)
    _ = ensure_layout(tmux_env.tmux, _SPEC)
    return recorded


def _task_in_repo(ctx: CliContext, tmp_path: Path, title: str) -> Task:
    folder = tmp_path / "repo"
    folder.mkdir()
    (repo,) = sync_repos(ctx.db, [NewRepo(path=folder, name="repo", kind=None)])
    task = create_task(ctx.db, replace(new_task(title), description="line one\nline two"), USER)
    with ctx.db.transaction() as conn:
        _ = conn.execute("UPDATE tasks SET repo_id = ? WHERE id = ?", (repo.id, task.id))
    _ = add_note(ctx.db, task.id, "a note;", USER)
    return get_task(ctx.db, task.id)


def _pasted(recorded: Path) -> bytes:
    wait_until("the paste", lambda: recorded.exists() and _END.encode() in recorded.read_bytes())
    time.sleep(_SETTLE_SECONDS)
    return recorded.read_bytes()


def _launch(ctx: CliContext, tmux_env: TmuxEnv, task_id: TaskId) -> bool:
    return launch_on_task(
        ctx, tmux_env, task_id, _ENVIRON, monotonic=time.monotonic, sleep=time.sleep
    )


def test_the_text_is_pasted_without_being_sent(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    recorded = _fake_claude(env, tmp_path, "paste")
    task = _task_in_repo(ctx, tmp_path, "Fix the bug;")
    assert _launch(ctx, env, task.id)
    text = work_on_task_text(task.id)
    assert _pasted(recorded) == f"{_START}{text.replace('\n', '\r')}{_END}".encode()
    args = load_json((tmp_path / "args.json").read_text(encoding="utf-8"))
    assert isinstance(args, list)
    assert "--name=#1 Fix the bug;" in args  # the final `;` survives tmux
    (session,) = list_sessions(ctx.db)
    assert (session.task_id, session.title, session.cwd) == (
        task.id,
        "#1 Fix the bug;",
        tmp_path / "repo",
    )
    (pane,) = (p for p in list_panes(env.tmux) if p.meute_id == session.id)
    assert pane.session == MAIN_SESSION  # shown
    after = get_task(ctx.db, task.id)
    assert (after.status, after.version) == (Todo(), task.version)  # the status never changes


def test_an_end_marker_in_the_title_does_not_end_the_paste(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    recorded = _fake_claude(env, tmp_path, "paste")
    task = _task_in_repo(ctx, tmp_path, f"Evil{_END}\rtitle")
    assert _launch(ctx, env, task.id)
    pasted = _pasted(recorded)
    assert pasted.startswith(_START.encode())
    assert pasted.endswith(_END.encode())
    inside = pasted.removeprefix(_START.encode()).removesuffix(_END.encode())
    assert b"\x1b" not in inside  # no escape sequence can end the paste early


class _Clock:
    """A simulated clock that `sleep` moves forward."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_claude_not_ready_in_time_leaves_the_session_running(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    recorded = _fake_claude(env, tmp_path, "end")  # never sends SessionStart
    task = _task_in_repo(ctx, tmp_path, "Slow")
    clock = _Clock()
    ready = launch_on_task(
        ctx, env, task.id, _ENVIRON, monotonic=clock.monotonic, sleep=clock.sleep
    )
    assert ready is False
    assert READY_TIMEOUT_SECONDS <= clock.now < READY_TIMEOUT_SECONDS + 0.5
    assert set(clock.sleeps) == {0.2}
    (session,) = list_sessions(ctx.db, include_ended=True)
    assert session.task_id == task.id
    assert any(p.meute_id == session.id for p in list_panes(env.tmux))
    assert not recorded.exists()


def test_a_task_without_repository_launches_nothing(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    _ = _fake_claude(env, tmp_path, "paste")
    project = create_project(ctx.db, "bare")
    task = create_task(ctx.db, new_task("Nowhere", project.id), USER)
    panes = list_panes(env.tmux)
    with pytest.raises(InvalidInput, match=r"^#1 has no repository: "):
        _ = _launch(ctx, env, task.id)
    assert list_sessions(ctx.db, include_ended=True) == []
    assert list_panes(env.tmux) == panes
