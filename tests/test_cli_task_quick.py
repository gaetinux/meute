"""`meute task quick`: the backend of the `M-t` window and its hidden command."""

import re
import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest

from conftest import Sandbox
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_show import show_session
from meute.cli.task_quick import CliQuickBackend, displayed_project
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.repos import sync_repos
from meute.core.db.tasks import history
from meute.core.errors import InvalidInput, MeuteError
from meute.core.paths import Paths
from meute.core.project import ProjectRef
from meute.core.repo import NewRepo
from meute.tmux.client import Tmux
from meute.tmux.layout import ensure_layout
from support import FIXED
from test_board_backend import _ENVIRON, env  # noqa: F401 — fixture reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixture reused
from test_board_backend_status import _SPEC  # pyright: ignore[reportPrivateUsage] — layout reused
from test_importtime import imported_roots


@pytest.fixture
def ctx(tmp_path: Path) -> Generator[CliContext]:
    with Database.open(tmp_path / "meute.db", busy_timeout_ms=1000, clock=lambda: FIXED) as db:
        yield CliContext(
            db=db,
            now=FIXED,
            actor=Actor(author=Author.USER, channel=Channel.CLI),
            config=Config(),
            paths=Paths.from_env({"XDG_STATE_HOME": str(tmp_path)}, home=tmp_path),
        )


def test_the_default_project_is_the_displayed_sessions(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    project = create_project(ctx.db, "meute")
    (repo,) = sync_repos(ctx.db, [NewRepo(path=tmp_path, name="Meute", kind=None)])
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, repo_id=repo.id), _ENVIRON)
    _ = ensure_layout(env.tmux, _SPEC)
    assert displayed_project(ctx, env.tmux) is None  # the welcome pane is shown
    show_session(ctx, env, session.id)
    assert displayed_project(ctx, env.tmux) == ProjectRef(id=project.id, name="meute")


def test_without_a_layout_or_a_server_there_is_no_default(
    ctx: CliContext,
    env: TmuxEnv,  # noqa: F811 — fixture
) -> None:
    assert displayed_project(ctx, env.tmux) is None
    gone = Tmux(socket="meute-test-no-such-server", config_file=None)
    assert displayed_project(ctx, gone) is None


def test_backend_context_and_creation_as_the_tui_user(ctx: CliContext) -> None:
    infra = create_project(ctx.db, "infra")
    ref = ProjectRef(id=infra.id, name="infra")
    backend = CliQuickBackend(ctx, ref)
    context = backend.context()
    assert (context.now, context.default, context.projects) == (FIXED, ref, (ref,))
    task = backend.create("Review !")
    assert task.project == ref
    (event,) = history(ctx.db, task.id)
    assert (event.author, event.channel) == (Author.USER, Channel.TUI)
    with pytest.raises(InvalidInput, match="unknown project"):
        _ = backend.create("x @nope")


def test_a_locked_database_is_a_meute_error(ctx: CliContext, tmp_path: Path) -> None:
    other = sqlite3.connect(tmp_path / "meute.db", isolation_level=None)
    try:
        _ = other.execute("BEGIN EXCLUSIVE")
        with pytest.raises(MeuteError, match="database is locked"):
            _ = CliQuickBackend(ctx, None).create("Review")
    finally:
        other.close()


ESCAPE = re.compile(r"\033\[[0-9;]*m")


@pytest.mark.parametrize("extra", [{}, {"GITHUB_ACTIONS": "true"}])  # CI: typer forces colours
def test_the_command_is_hidden(sandbox: Sandbox, extra: dict[str, str]) -> None:
    listed = ESCAPE.sub("", sandbox.run("task", "--help", env=extra).stdout)
    assert "│ list " in listed  # witness: the commands are listed this way
    assert "│ quick " not in listed
    assert sandbox.run("task", "quick", "--help").returncode == 0


def test_the_command_keeps_textual_out_of_start_up() -> None:
    assert "textual" not in imported_roots(["task", "quick", "--help"], "")
