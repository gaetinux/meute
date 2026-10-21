"""Resuming an ended Claude session with `claude --resume`, on a throw-away tmux server."""

from pathlib import Path

import pytest

from conftest import FAKE_CLAUDE_DIR, Sandbox
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash, session_spawn
from meute.cli.session_resume import resume_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.claude_session import ClaudeDetails
from meute.core.config import Config
from meute.core.db.claude_sessions import get_claude_details
from meute.core.db.connection import Database
from meute.core.db.sessions import get_session, list_sessions, set_session_state
from meute.core.errors import InvalidInput
from meute.core.paths import Paths
from meute.core.session import Session, SessionId
from meute.core.session_state import Exited, Idle, Unknown
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.names import BG_SESSION
from meute.tmux.panes import Spawn, kill_pane, pane_of_session, respawn_window, spawn_window
from support import FIXED, load_json, wait_until

_SPEC = LayoutSpec(
    board_width=60,
    narrow_threshold=100,
    board_command=("true",),
    welcome_command=("true",),
    sync_command=("true",),
    keys=Keys(focus_board="M-p", focus_main="M-o"),
)


def _ctx(sandbox: Sandbox) -> tuple[CliContext, TmuxEnv, dict[str, str]]:
    db = Database.open(
        sandbox.root / "data/meute/meute.db", busy_timeout_ms=1000, clock=lambda: FIXED
    )
    paths = Paths.from_env(
        {
            "XDG_CONFIG_HOME": str(sandbox.root / "config"),
            "XDG_DATA_HOME": str(sandbox.root / "data"),
            "XDG_STATE_HOME": str(sandbox.root / "state"),
        },
        home=sandbox.root / "home",
    )
    ctx = CliContext(
        db=db,
        now=FIXED,
        actor=Actor(author=Author.USER, channel=Channel.CLI),
        config=Config(),
        paths=paths,
    )
    env = TmuxEnv(tmux=sandbox.tmux(), spec=_SPEC, config_file=sandbox.root / "tmux.conf")
    return ctx, env, {"PATH": f"{FAKE_CLAUDE_DIR}:/usr/bin:/bin", "SHELL": "/bin/sh"}


def _ended_claude(sandbox: Sandbox) -> Session:
    """A Claude session that started and ended (fake `exit` script): native id known, pane dead."""
    folder = sandbox.root / "w"
    folder.mkdir(exist_ok=True)
    args = sandbox.root / "args.json"
    env = {"MEUTE_FAKE_CLAUDE_SCRIPT": "exit", "MEUTE_FAKE_CLAUDE_ARGS": str(args)}
    result = sandbox.run("session", "new", "--cwd", str(folder), "--title", "trial", env=env)
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (first,) = list_sessions(db)

    def ended() -> bool:
        with sandbox.db() as db:
            return isinstance(get_session(db, first.id).state, Exited) and (
                get_claude_details(db, first.id).native_id is not None
            )

    wait_until("the session to end", ended, timeout=30)
    with sandbox.db() as db:
        return get_session(db, first.id)


def _script(sandbox: Sandbox, name: str) -> None:
    """Pick the fake claude script of the panes started from now on."""
    _ = sandbox.tmux().run("set-environment", "-g", "MEUTE_FAKE_CLAUDE_SCRIPT", name)


def _args(sandbox: Sandbox) -> list[str]:
    loaded = load_json((sandbox.root / "args.json").read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    return [str(item) for item in loaded]


def _state(sandbox: Sandbox, session_id: SessionId) -> object:
    with sandbox.db() as db:
        return get_session(db, session_id).state


def _details(sandbox: Sandbox, session_id: SessionId) -> ClaudeDetails:
    with sandbox.db() as db:
        return get_claude_details(db, session_id)


def test_resume_with_a_dead_pane_reuses_the_pane(sandbox: Sandbox) -> None:
    session = _ended_claude(sandbox)
    native = _details(sandbox, session.id).native_id
    with sandbox.db() as db:
        _ = db.conn.execute("UPDATE sessions SET permission_mode = 'plan'")
        db.conn.commit()
    ctx, env, environ = _ctx(sandbox)
    before = pane_of_session(env.tmux, session.id)
    assert before is not None
    assert before.dead
    _script(sandbox, "permission")
    try:
        resumed = resume_session(ctx, env, session.id, environ)
        assert resumed.state == Unknown()
        assert resumed.ended_at is None
        assert resumed.id == session.id
        after = pane_of_session(env.tmux, session.id)
        assert after is not None
        assert after.id == before.id
        wait_until(
            "the resumed hooks", lambda: _state(sandbox, session.id) != Unknown(), timeout=30
        )
    finally:
        ctx.db.close()
    args = _args(sandbox)
    assert args[args.index("--resume") + 1] == native
    assert "--session-id" not in args
    assert args[args.index("--permission-mode") + 1] == "plan"
    assert args[-1] == "--name=trial"
    assert _details(sandbox, session.id).native_id == native


def test_resume_without_a_pane_opens_a_window_in_the_background_session(
    sandbox: Sandbox,
) -> None:
    session = _ended_claude(sandbox)
    ctx, env, environ = _ctx(sandbox)
    old = pane_of_session(env.tmux, session.id)
    assert old is not None
    _ = spawn_window(  # keeps the tmux server alive once the dead pane is gone
        env.tmux, Spawn(session="keeper", cwd=Path("/"), command=("sleep", "3600"))
    )
    kill_pane(env.tmux, old.id)
    _script(sandbox, "permission")
    try:
        _ = resume_session(ctx, env, session.id, environ)
        pane = pane_of_session(env.tmux, session.id)
        assert pane is not None
        assert (pane.session, pane.dead) == (BG_SESSION, False)
        wait_until(
            "the resumed hooks", lambda: _state(sandbox, session.id) != Unknown(), timeout=30
        )
    finally:
        ctx.db.close()
    assert "--resume" in _args(sandbox)


def test_a_conversation_claude_cannot_find_leaves_a_dead_pane_and_can_be_resumed_again(
    sandbox: Sandbox,
) -> None:
    session = _ended_claude(sandbox)  # the fake exits at once, like claude on a lost transcript
    ctx, env, environ = _ctx(sandbox)
    try:
        for _ in range(2):
            _ = resume_session(ctx, env, session.id, environ)
            wait_until(
                "the session to be exited again",
                lambda: isinstance(_state(sandbox, session.id), Exited),
                timeout=30,
            )
            pane = pane_of_session(env.tmux, session.id)
            assert pane is not None
            wait_until(
                "the pane to be dead",
                lambda: (p := pane_of_session(env.tmux, session.id)) is not None and p.dead,
            )
    finally:
        ctx.db.close()


def test_refusals_launch_nothing_and_write_nothing(sandbox: Sandbox) -> None:
    ended = _ended_claude(sandbox)
    ctx, env, environ = _ctx(sandbox)
    try:
        bash = launch_bash(ctx, env, BashLaunch(cwd=sandbox.root / "w"), environ)
        _ = set_session_state(ctx.db, bash.id, Exited(code=0))
        with pytest.raises(InvalidInput, match=r"^only Claude sessions resume$"):
            _ = resume_session(ctx, env, bash.id, environ)

        _ = ctx.db.conn.execute("UPDATE sessions SET native_id = NULL WHERE id = ?", (ended.id,))
        with pytest.raises(
            InvalidInput, match=r'^"trial" cannot be resumed: Claude never confirmed its id$'
        ):
            _ = resume_session(ctx, env, ended.id, environ)
        for hostile in ("--dangerous", "a b", ""):
            _ = ctx.db.conn.execute(
                "UPDATE sessions SET native_id = ? WHERE id = ?", (hostile, ended.id)
            )
            with pytest.raises(InvalidInput, match=r"cannot be resumed"):
                _ = resume_session(ctx, env, ended.id, environ)
        _ = ctx.db.conn.execute("UPDATE sessions SET native_id = 'abc' WHERE id = ?", (ended.id,))

        _ = set_session_state(ctx.db, ended.id, Idle())
        with pytest.raises(InvalidInput, match=r'^"trial" is still running$'):
            _ = resume_session(ctx, env, ended.id, environ)
        _ = set_session_state(ctx.db, ended.id, Exited(code=7))
        before = get_session(ctx.db, ended.id)

        (sandbox.root / "w").rmdir()
        with pytest.raises(InvalidInput, match=r"^folder not found: "):
            _ = resume_session(ctx, env, ended.id, environ)
        assert get_session(ctx.db, ended.id) == before

        (sandbox.root / "w").mkdir()
        with pytest.raises(InvalidInput, match=r"^claude not found: "):
            _ = resume_session(ctx, env, ended.id, {"PATH": str(Path("/nonexistent"))})
        assert get_session(ctx.db, ended.id) == before
        pane = pane_of_session(env.tmux, ended.id)
        assert pane is not None
        assert pane.dead
    finally:
        ctx.db.close()


def test_an_ended_session_with_a_live_pane_is_refused_and_nothing_starts(
    sandbox: Sandbox,
) -> None:
    session = _ended_claude(sandbox)
    ctx, env, environ = _ctx(sandbox)
    try:
        wait_until(
            "the pane to be dead",
            lambda: (p := pane_of_session(env.tmux, session.id)) is not None and p.dead,
        )
        dead = pane_of_session(env.tmux, session.id)
        assert dead is not None
        spawn = session_spawn(session.id, sandbox.root / "w", ("sleep", "3600"))
        _ = respawn_window(env.tmux, dead.id, spawn)  # the pane lives again, the state is Exited
        before = get_session(ctx.db, session.id)
        args = sandbox.root / "args.json"
        args.unlink()
        with pytest.raises(InvalidInput, match=r'^"trial" is still running$'):
            _ = resume_session(ctx, env, session.id, environ)
        pane = pane_of_session(env.tmux, session.id)
        assert pane is not None
        assert (pane.id, pane.dead) == (dead.id, False)
        assert get_session(ctx.db, session.id) == before
        assert not args.exists()
    finally:
        ctx.db.close()


def test_the_launched_pane_is_killed_when_reopening_fails(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _ended_claude(sandbox)
    ctx, env, environ = _ctx(sandbox)

    def refuse(_db: Database, _session_id: SessionId) -> Session:
        message = "database is locked"
        raise InvalidInput(message)

    monkeypatch.setattr("meute.cli.session_resume.reopen_session", refuse)
    _ = spawn_window(  # keeps the tmux server alive once the pane is killed
        env.tmux, Spawn(session="keeper", cwd=Path("/"), command=("sleep", "3600"))
    )
    _script(sandbox, "permission")
    try:
        with pytest.raises(InvalidInput, match="database is locked"):
            _ = resume_session(ctx, env, session.id, environ)
        assert pane_of_session(env.tmux, session.id) is None
    finally:
        ctx.db.close()
