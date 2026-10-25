"""A new session in a known repository without a project creates it."""

from pathlib import Path

import pytest

from conftest import Sandbox
from meute.cli.context import CliContext
from meute.cli.launch_project import launch_project
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_launch_claude import ClaudeLaunch, launch_claude
from meute.cli.session_resume import resume_session
from meute.core.db.projects import (
    create_project,
    list_projects,
    project_by_name,
    set_project_instructions,
)
from meute.core.db.repos import link_repo, repo_project_links, sync_repos
from meute.core.db.sessions import get_session, list_sessions
from meute.core.db.tasks import create_task
from meute.core.errors import InvalidInput
from meute.core.project import RepoId
from meute.core.repo import NewRepo
from meute.core.session_state import Exited
from meute.tmux.errors import TmuxError
from meute.tmux.panes import pane_of_session
from support import USER, new_task, wait_until
from test_launch_context import _ctx, _environ, _recorded  # pyright: ignore[reportPrivateUsage] — shared helpers


def _repo(
    ctx: CliContext, root: Path, name: str, *, folder: str | None = None
) -> tuple[Path, RepoId]:
    path = (root / (folder or name)).resolve()
    path.mkdir(parents=True, exist_ok=True)
    found = NewRepo(path=path, name=name, kind=None)
    repos = sync_repos(ctx.db, [found])
    return path, next(r.id for r in repos if r.path == path)


def test_bash_then_claude_in_a_repository_without_a_project_create_it_once(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        folder, repo_id = _repo(ctx, sandbox.root, "alpha")
        environ = _environ(sandbox, monkeypatch, args)
        bash = launch_bash(ctx, env, BashLaunch(cwd=folder, repo_id=repo_id), environ)
        claude = launch_claude(ctx, env, ClaudeLaunch(cwd=folder, repo_id=repo_id), environ)
        project = project_by_name(ctx.db, "alpha")
        assert project is not None
        assert [p.name for p in list_projects(ctx.db)] == ["alpha"]
        assert repo_project_links(ctx.db) == {repo_id: project.id}
        assert bash.project_id == project.id
        assert claude.project_id == project.id
        assert {s.project_id for s in list_sessions(ctx.db, include_ended=True)} == {project.id}
    finally:
        ctx.db.close()


def test_the_task_project_wins_and_no_project_is_made_for_the_repository(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        folder, repo_id = _repo(ctx, sandbox.root, "web")
        api = create_project(ctx.db, "api")
        task = create_task(ctx.db, new_task("Do it", api.id), USER)
        session = launch_claude(
            ctx,
            env,
            ClaudeLaunch(cwd=folder, repo_id=repo_id, task_id=task.id),
            _environ(sandbox, monkeypatch, args),
        )
        assert session.project_id == api.id
        assert project_by_name(ctx.db, "web") is None
    finally:
        ctx.db.close()


def test_two_repositories_of_a_name_and_a_project_with_another_case_make_no_project(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        existing = create_project(ctx.db, "Web")
        _ = _repo(ctx, sandbox.root, "web", folder="one/web")
        folder, repo_id = _repo(ctx, sandbox.root, "web", folder="two/web")
        session = launch_bash(
            ctx, env, BashLaunch(cwd=folder, repo_id=repo_id), _environ(sandbox, monkeypatch, args)
        )
        assert [p.id for p in list_projects(ctx.db)] == [existing.id]
        assert session.project_id == existing.id
    finally:
        ctx.db.close()


def test_a_folder_outside_any_repository_creates_nothing(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        folder = sandbox.root / "loose"
        folder.mkdir()
        environ = _environ(sandbox, monkeypatch, args)
        bash = launch_bash(ctx, env, BashLaunch(cwd=folder), environ)
        claude = launch_claude(ctx, env, ClaudeLaunch(cwd=folder), environ)
        assert list_projects(ctx.db) == []
        assert (bash.project_id, claude.project_id) == (None, None)
    finally:
        ctx.db.close()


def test_a_missing_folder_creates_no_project(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        folder, repo_id = _repo(ctx, sandbox.root, "gone")
        folder.rmdir()
        with pytest.raises(InvalidInput, match="folder not found"):
            _ = launch_bash(
                ctx,
                env,
                BashLaunch(cwd=folder, repo_id=repo_id),
                _environ(sandbox, monkeypatch, args),
            )
        assert list_projects(ctx.db) == []
    finally:
        ctx.db.close()


def test_the_composed_context_reads_the_instructions_of_the_found_project(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        folder, repo_id = _repo(ctx, sandbox.root, "alpha")
        project = create_project(ctx.db, "Project A")
        _ = set_project_instructions(ctx.db, project.id, "be careful")
        link_repo(ctx.db, project.id, repo_id)
        session = launch_claude(
            ctx,
            env,
            ClaudeLaunch(cwd=folder, repo_id=repo_id),
            _environ(sandbox, monkeypatch, args),
        )
        assert session.project_id == project.id
    finally:
        ctx.db.close()
    assert _recorded(args)[-2].endswith("Project instructions (Project A):\nbe careful")


def test_a_tmux_failure_keeps_the_project_and_records_no_session(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)

    def failing(*_args: object, **_kwargs: object) -> str:
        message = "boom"
        raise TmuxError(message)

    monkeypatch.setattr("meute.cli.session_launch.spawn_window", failing)
    try:
        folder, repo_id = _repo(ctx, sandbox.root, "alpha")
        with pytest.raises(TmuxError):
            _ = launch_bash(
                ctx,
                env,
                BashLaunch(cwd=folder, repo_id=repo_id),
                _environ(sandbox, monkeypatch, args),
            )
        assert project_by_name(ctx.db, "alpha") is not None
        assert list_sessions(ctx.db, include_ended=True) == []
    finally:
        ctx.db.close()


def test_resuming_a_session_creates_no_project(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        folder, repo_id = _repo(ctx, sandbox.root, "alpha")
        environ = _environ(sandbox, monkeypatch, args)
        session = launch_claude(ctx, env, ClaudeLaunch(cwd=folder, repo_id=repo_id), environ)
        # forget the project: a session from before this feature
        ctx.db.conn.execute("UPDATE sessions SET project_id = NULL")
        ctx.db.conn.execute("DELETE FROM project_repos")
        ctx.db.conn.execute("DELETE FROM projects")
        ctx.db.conn.commit()
        _ = _recorded(args)

        def ended() -> bool:
            pane = pane_of_session(env.tmux, session.id)
            return isinstance(get_session(ctx.db, session.id).state, Exited) and (
                pane is not None and pane.dead
            )

        wait_until("the session to end", ended, timeout=30)
        args.unlink()
        _ = resume_session(ctx, env, session.id, environ)
        assert list_projects(ctx.db) == []
    finally:
        ctx.db.close()


def test_a_blank_repository_name_creates_no_project(sandbox: Sandbox) -> None:
    ctx, _ = _ctx(sandbox)
    try:
        _, repo_id = _repo(ctx, sandbox.root, "   ", folder="blank")
        assert launch_project(ctx, repo_id=repo_id, task_id=None) is None
        assert list_projects(ctx.db) == []
    finally:
        ctx.db.close()
