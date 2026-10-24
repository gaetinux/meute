"""Reopening a saved state, on a throw-away tmux server with the fake claude."""

import json
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest

from conftest import FAKE_CLAUDE_DIR, Sandbox
from meute.cli.context import CliContext
from meute.cli.session_launch_claude import CLAUDE_MISSING
from meute.cli.session_show import show_session
from meute.cli.state_reopen import ReopenReport, reopen_state
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.db.claude_sessions import get_claude_details
from meute.core.db.repos import sync_repos
from meute.core.db.saved_states import get_state, save_state
from meute.core.db.sessions import get_session, list_sessions
from meute.core.paths import Paths
from meute.core.repo import NewRepo
from meute.core.saved_state import SavedSession, SavedState
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import Exited, Running, Unknown
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.layout import displayed_meute_id, ensure_layout
from meute.tmux.panes import kill_pane, pane_of_session
from support import FIXED, saved_session, wait_until

_SLEEP = ("sh", "-c", "sleep 3600")
_SPEC = LayoutSpec(
    board_width=60,
    narrow_threshold=100,
    board_command=_SLEEP,
    welcome_command=_SLEEP,
    sync_command=("true",),
    keys=Keys(focus_board="M-p", focus_main="M-o"),
)
_ENVIRON = {"PATH": f"{FAKE_CLAUDE_DIR}:/usr/bin:/bin", "SHELL": "/bin/sh"}
_GHOST = SessionId("aaaa1111-0000-4000-8000-000000000000")


@pytest.fixture
def ctx(sandbox: Sandbox) -> Generator[CliContext]:
    """A context on the sandbox database, created by a first command."""
    assert sandbox.run("session", "list").returncode == 0
    paths = Paths.from_env(
        {
            "XDG_CONFIG_HOME": str(sandbox.root / "config"),
            "XDG_DATA_HOME": str(sandbox.root / "data"),
            "XDG_STATE_HOME": str(sandbox.root / "state"),
        },
        home=sandbox.root / "home",
    )
    with sandbox.db() as db:
        yield CliContext(
            db=db,
            now=FIXED,
            actor=Actor(author=Author.USER, channel=Channel.CLI),
            config=Config(),
            paths=paths,
        )


@pytest.fixture
def env(sandbox: Sandbox) -> TmuxEnv:
    return TmuxEnv(tmux=sandbox.tmux(), spec=_SPEC, config_file=sandbox.root / "tmux.conf")


def _folder(sandbox: Sandbox, name: str) -> Path:
    folder = sandbox.root / name
    folder.mkdir(exist_ok=True)
    return folder


def _session(sandbox: Sandbox, title: str) -> Session:
    with sandbox.db() as db:
        (session,) = (s for s in list_sessions(db, include_ended=True) if s.title == title)
    return session


def _ended_bash(sandbox: Sandbox, title: str, folder: Path) -> Session:
    """A Bash session whose pane was killed: it is no longer live once reconciled."""
    result = sandbox.run(
        "session", "new", "--kind", "bash", "--cwd", str(folder), "--title", title
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    session = _session(sandbox, title)
    pane = pane_of_session(sandbox.tmux(), session.id)
    assert pane is not None
    kill_pane(sandbox.tmux(), pane.id)
    return session


def _ended_claude(sandbox: Sandbox, title: str, folder: Path) -> Session:
    """A Claude session that started then ended (fake `exit` script): its Claude id is known."""
    env = {"MEUTE_FAKE_CLAUDE_SCRIPT": "exit"}
    result = sandbox.run("session", "new", "--cwd", str(folder), "--title", title, env=env)
    assert result.returncode == 0, result.stderr
    session = _session(sandbox, title)

    def ended() -> bool:
        with sandbox.db() as db:
            return isinstance(get_session(db, session.id).state, Exited) and (
                get_claude_details(db, session.id).native_id is not None
            )

    wait_until("the session to end", ended, timeout=30)
    _ = sandbox.tmux().run("set-environment", "-g", "MEUTE_FAKE_CLAUDE_SCRIPT", "permission")
    return session


def _saved(
    session: Session, *, displayed: bool = False, native_id: str | None = None
) -> SavedSession:
    return saved_session(
        session.id,
        title=session.title,
        cwd=session.cwd,
        agent=session.agent,
        native_id=native_id,
        task_id=session.task_id,
        repo_id=session.repo_id,
        displayed=displayed,
    )


def _state(*sessions: SavedSession) -> SavedState:
    return SavedState(name="work", created_at=FIXED, sessions=sessions)


def _live_bash(ctx: CliContext, title: str) -> list[Session]:
    return [
        s
        for s in list_sessions(ctx.db)
        if s.agent is AgentKind.BASH and s.title == title and s.state == Running()
    ]


def test_claude_is_resumed_bash_restarted_and_the_displayed_one_shown(
    sandbox: Sandbox, ctx: CliContext, env: TmuxEnv
) -> None:
    folder = _folder(sandbox, "w")
    claude = _ended_claude(sandbox, "agent", folder)
    bash = _ended_bash(sandbox, "shell", folder)
    _ = ensure_layout(env.tmux, env.spec)
    state = _state(_saved(claude), _saved(bash, displayed=True))
    report = reopen_state(ctx, env, _ENVIRON, state)
    assert report == ReopenReport(reopened=2, skipped=())
    resumed = get_session(ctx.db, claude.id)
    assert resumed.state == Unknown()
    assert resumed.ended_at is None
    (fresh,) = _live_bash(ctx, "shell")
    assert fresh.id != bash.id
    assert fresh.cwd == folder.resolve()
    assert displayed_meute_id(env.tmux) == fresh.id


def test_a_second_reopening_skips_everything_as_already_running(
    sandbox: Sandbox, ctx: CliContext, env: TmuxEnv
) -> None:
    folder = _folder(sandbox, "w")
    claude = _ended_claude(sandbox, "agent", folder)
    bash = _ended_bash(sandbox, "shell", folder)
    _ = ensure_layout(env.tmux, env.spec)
    state = _state(_saved(claude), _saved(bash, displayed=True))
    _ = reopen_state(ctx, env, _ENVIRON, state)
    (fresh,) = _live_bash(ctx, "shell")
    show_session(ctx, env, claude.id)
    report = reopen_state(ctx, env, _ENVIRON, state)
    assert report == ReopenReport(
        reopened=0, skipped=(("agent", "already running"), ("shell", "already running"))
    )
    assert len(_live_bash(ctx, "shell")) == 1
    assert displayed_meute_id(env.tmux) == fresh.id


def test_a_bash_whose_folder_has_another_live_bash_is_already_running(
    sandbox: Sandbox, ctx: CliContext, env: TmuxEnv
) -> None:
    folder = _folder(sandbox, "w")
    ended = _ended_bash(sandbox, "shell", folder)
    result = sandbox.run(
        "session", "new", "--kind", "bash", "--cwd", str(folder), "--title", "other"
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    (other,) = _live_bash(ctx, "other")
    assert other.id != ended.id
    report = reopen_state(ctx, env, _ENVIRON, _state(_saved(ended)))
    assert report == ReopenReport(reopened=0, skipped=(("shell", "already running"),))
    assert _live_bash(ctx, "shell") == []
    assert [s.id for s in list_sessions(ctx.db) if s.state == Running()] == [other.id]


def test_claude_without_a_conversation_id_or_row_is_skipped(
    sandbox: Sandbox, ctx: CliContext, env: TmuxEnv
) -> None:
    folder = _folder(sandbox, "w")
    claude = _ended_claude(sandbox, "agent", folder)
    _ = ctx.db.conn.execute("UPDATE sessions SET native_id = NULL")
    ctx.db.conn.commit()
    ghost = saved_session(
        _GHOST, title="ghost", cwd=folder, agent=AgentKind.CLAUDE, native_id="native-1"
    )
    report = reopen_state(ctx, env, _ENVIRON, _state(_saved(claude), ghost))
    assert report == ReopenReport(
        reopened=0, skipped=(("agent", "no conversation id"), ("ghost", "no conversation id"))
    )


def test_a_vanished_folder_is_skipped_before_any_launch(
    sandbox: Sandbox, ctx: CliContext, env: TmuxEnv
) -> None:
    claude = _ended_claude(sandbox, "agent", _folder(sandbox, "c"))
    bash = _ended_bash(sandbox, "shell", _folder(sandbox, "b"))
    shutil.rmtree(sandbox.root / "c")
    shutil.rmtree(sandbox.root / "b")
    report = reopen_state(ctx, env, _ENVIRON, _state(_saved(claude), _saved(bash)))
    assert report == ReopenReport(
        reopened=0,
        skipped=(
            ("agent", f"folder not found: {sandbox.root / 'c'}"),
            ("shell", f"folder not found: {sandbox.root / 'b'}"),
        ),
    )
    assert _live_bash(ctx, "shell") == []


def test_a_missing_claude_skips_only_the_claude_session(
    sandbox: Sandbox, ctx: CliContext, env: TmuxEnv
) -> None:
    folder = _folder(sandbox, "w")
    claude = _ended_claude(sandbox, "agent", folder)
    bash = _ended_bash(sandbox, "shell", folder)
    without_claude = {"PATH": "/usr/bin:/bin", "SHELL": "/bin/sh"}
    report = reopen_state(ctx, env, without_claude, _state(_saved(claude), _saved(bash)))
    assert report == ReopenReport(reopened=1, skipped=(("agent", CLAUDE_MISSING),))
    assert len(_live_bash(ctx, "shell")) == 1


def test_bash_keeps_its_title_and_repository(
    sandbox: Sandbox, ctx: CliContext, env: TmuxEnv
) -> None:
    folder = _folder(sandbox, "r")
    (repo,) = sync_repos(ctx.db, [NewRepo(path=folder.resolve(), name="r", kind=None)])
    bash = _ended_bash(sandbox, "shell", folder)
    entry = saved_session(bash.id, title="kept title", cwd=bash.cwd, repo_id=repo.id)
    assert reopen_state(ctx, env, _ENVIRON, _state(entry)).reopened == 1
    (fresh,) = _live_bash(ctx, "kept title")
    assert fresh.repo_id == repo.id


def test_an_entry_with_an_unknown_agent_does_not_stop_the_others(
    sandbox: Sandbox, ctx: CliContext, env: TmuxEnv
) -> None:
    bash = _ended_bash(sandbox, "shell", _folder(sandbox, "w"))
    _ = save_state(ctx.db, "work", [_saved(bash)])
    _ = ctx.db.conn.execute(
        "UPDATE saved_states SET sessions = json_insert(sessions, '$[#]', json(?))",
        (json.dumps({"session_id": _GHOST, "agent": "zsh", "cwd": "/", "native_id": None,
                     "title": "odd", "task_id": None, "repo_id": None, "displayed": False}),),
    )  # fmt: skip
    ctx.db.conn.commit()
    report = reopen_state(ctx, env, _ENVIRON, get_state(ctx.db, "work"))
    assert report == ReopenReport(reopened=1, skipped=())


def test_meute_not_open_leaves_the_report_unchanged(
    sandbox: Sandbox, ctx: CliContext, env: TmuxEnv
) -> None:
    bash = _ended_bash(sandbox, "shell", _folder(sandbox, "w"))
    report = reopen_state(ctx, env, _ENVIRON, _state(_saved(bash, displayed=True)))
    assert report == ReopenReport(reopened=1, skipped=())
