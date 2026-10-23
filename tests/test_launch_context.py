"""The MCP configuration and the composed context reach the Claude command line."""

import stat
from pathlib import Path

import pytest

from conftest import FAKE_CLAUDE_DIR, Sandbox
from meute.claude.context_arg import ContextText
from meute.claude.launch import claude_argv
from meute.claude.mcp_config import mcp_config_document
from meute.claude.settings import MEUTE_TOOLS, settings_document
from meute.cli.context import CliContext
from meute.cli.session_context import session_context
from meute.cli.session_launch_claude import ClaudeLaunch, launch_claude
from meute.cli.session_resume import resume_session
from meute.cli.tmux_env import TmuxEnv, meute_command
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.context import CONTRADICTION_RULE, task_line
from meute.core.db.connection import Database
from meute.core.db.projects import create_project, set_project_instructions
from meute.core.db.repos import create_repo_project, sync_repos
from meute.core.db.sessions import get_session, list_sessions
from meute.core.paths import Paths
from meute.core.repo import NewRepo
from meute.core.session import SessionId
from meute.core.session_state import Exited
from meute.core.task import TaskId
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.panes import pane_of_session
from support import FIXED, load_json, wait_until

SID = SessionId("0b6f1d0e-0000-4000-8000-000000000003")
_SPEC = LayoutSpec(
    board_width=40,
    narrow_threshold=100,
    board_command=("true",),
    welcome_command=("true",),
    sync_command=("true",),
    keys=Keys(focus_board="M-p", focus_main="M-o"),
)
LONG = "--x leading dash\nline two;\n" + "z" * 20_000 + "\n;"
NASTY = "--x leading dash\nline two;\n" + "y" * 6_000 + "\n;"


def test_argv_puts_mcp_config_after_settings_and_context_before_the_name() -> None:
    argv = claude_argv(
        claude=Path("/bin/claude"),
        settings=Path("/s/settings.json"),
        session_id=SID,
        permission_mode="plan",
        title="Fix it",
        mcp_config=Path("/s/mcp.json"),
        context=ContextText("the context"),
    )
    assert argv == (
        "/bin/claude", "--settings", "/s/settings.json", "--mcp-config", "/s/mcp.json",
        "--session-id", SID, "--permission-mode", "plan",
        "--append-system-prompt", "the context", "--name=Fix it",
    )  # fmt: skip


def _ctx(sandbox: Sandbox, config: Config | None = None) -> tuple[CliContext, TmuxEnv]:
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
        config=config or Config(),
        paths=paths,
    )
    env = TmuxEnv(tmux=sandbox.tmux(), spec=_SPEC, config_file=sandbox.root / "tmux.conf")
    return ctx, env


def _environ(sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch, args: Path) -> dict[str, str]:
    """The environment for `claude`; the tmux server started by the launch inherits the fake's."""
    monkeypatch.setenv("MEUTE_FAKE_CLAUDE_ARGS", str(args))
    monkeypatch.setenv("MEUTE_FAKE_CLAUDE_SCRIPT", "exit")
    for name, folder in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_STATE_HOME", "state"),
    ):
        monkeypatch.setenv(name, str(sandbox.root / folder))
    monkeypatch.setenv("HOME", str(sandbox.root / "home"))
    monkeypatch.setenv("MEUTE_NOW", "2026-10-14T10:30[Europe/Paris]")
    monkeypatch.setenv("MEUTE_TMUX_SOCKET", sandbox.tmux_socket)
    return {"PATH": f"{FAKE_CLAUDE_DIR}:/usr/bin:/bin", "SHELL": "/bin/sh"}


def _recorded(args: Path) -> list[str]:
    wait_until("the fake claude to record its arguments", args.exists, timeout=30)
    loaded = load_json(args.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    return [str(item) for item in loaded]


def _repo_project(ctx: CliContext, folder: Path, instructions: str) -> NewRepo:
    found = NewRepo(path=folder, name=folder.name, kind=None)
    _ = sync_repos(ctx.db, [found])
    project = create_repo_project(ctx.db, folder.name)
    _ = set_project_instructions(ctx.db, project.id, instructions)
    return found


def test_context_is_none_without_any_instructions_or_task(sandbox: Sandbox) -> None:
    ctx, _ = _ctx(sandbox)
    try:
        assert (
            session_context(ctx, instructions="", project_id=None, repo_id=None, task_id=None)
            is None
        )
    finally:
        ctx.db.close()


def test_context_resolves_the_project_by_id_then_by_repository_name(sandbox: Sandbox) -> None:
    folder = sandbox.root / "w"
    folder.mkdir()
    ctx, _ = _ctx(sandbox)
    try:
        by_id = create_project(ctx.db, "other")
        _ = set_project_instructions(ctx.db, by_id.id, "from other")
        (repo,) = sync_repos(ctx.db, [NewRepo(path=folder, name="w", kind=None)])
        named = create_project(ctx.db, "W")
        _ = set_project_instructions(ctx.db, named.id, "from w")
        task = TaskId(3)
        found = session_context(
            ctx, instructions="be kind", project_id=by_id.id, repo_id=repo.id, task_id=task
        )
        assert found == (
            f"{CONTRADICTION_RULE}\n\nGlobal instructions:\nbe kind\n\n"
            f"Project instructions (other):\nfrom other\n\n{task_line(task)}"
        )
        text = session_context(
            ctx, instructions="be kind", project_id=None, repo_id=repo.id, task_id=None
        )
        assert text is not None
        assert text.endswith("Project instructions (W):\nfrom w")
    finally:
        ctx.db.close()


def test_launch_passes_mcp_config_and_the_context_intact(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = (sandbox.root / "w").resolve()
    folder.mkdir()
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        _ = _repo_project(ctx, folder, NASTY)
        (repo,) = (r for r in sync_repos(ctx.db, []) if r.name == "w")
        session = launch_claude(
            ctx,
            env,
            ClaudeLaunch(cwd=folder, title="t", repo_id=repo.id),
            _environ(sandbox, monkeypatch, args),
        )
    finally:
        ctx.db.close()
    argv = _recorded(args)
    session_dir = sandbox.root / "state/meute/sessions" / session.id
    assert argv[argv.index("--settings") + 2 : argv.index("--settings") + 4] == [
        "--mcp-config",
        str(session_dir / "mcp.json"),
    ]
    command = meute_command()
    mcp_file = (session_dir / "mcp.json").read_text(encoding="utf-8")
    assert load_json(mcp_file) == mcp_config_document(command, session.id)
    context = argv[argv.index("--append-system-prompt") + 1]
    assert context.endswith("Project instructions (w):\n" + NASTY.strip())
    assert argv[-2:] == [context, "--name=t"]
    settings_file = (session_dir / "settings.json").read_text(encoding="utf-8")
    assert load_json(settings_file) == settings_document(command, MEUTE_TOOLS)


def test_no_instructions_and_no_task_means_no_context_option(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = (sandbox.root / "w").resolve()
    folder.mkdir()
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        _ = launch_claude(ctx, env, ClaudeLaunch(cwd=folder), _environ(sandbox, monkeypatch, args))
    finally:
        ctx.db.close()
    assert "--append-system-prompt" not in _recorded(args)


def test_resume_recomputes_the_context_from_the_current_instructions(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = (sandbox.root / "w").resolve()
    folder.mkdir()
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        _ = _repo_project(ctx, folder, "first")
        (repo,) = (r for r in sync_repos(ctx.db, []) if r.name == "w")
        environ = _environ(sandbox, monkeypatch, args)
        session = launch_claude(ctx, env, ClaudeLaunch(cwd=folder, repo_id=repo.id), environ)

        def ended() -> bool:
            row = get_session(ctx.db, session.id)
            pane = pane_of_session(env.tmux, session.id)
            return isinstance(row.state, Exited) and pane is not None and pane.dead

        wait_until("the session to end", ended, timeout=30)
        assert _recorded(args)[-2].endswith("Project instructions (w):\nfirst")
        args.unlink()
        project = create_repo_project(ctx.db, "w")
        _ = set_project_instructions(ctx.db, project.id, "second")
        _ = resume_session(ctx, env, session.id, environ)
        resumed = _recorded(args)
    finally:
        ctx.db.close()
    assert "--resume" in resumed
    assert resumed[-2].endswith("Project instructions (w):\nsecond")
    assert resumed[resumed.index("--settings") + 2] == "--mcp-config"
    assert len(list_sessions_safe(sandbox)) == 1


def list_sessions_safe(sandbox: Sandbox) -> list[object]:
    with sandbox.db() as db:
        return list(list_sessions(db))


def _long_to_short(sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], Path]:
    """Launch with 20 000 characters of instructions, then resume after they were shortened."""
    folder = (sandbox.root / "w").resolve()
    folder.mkdir()
    args = sandbox.root / "args.json"
    ctx, env = _ctx(sandbox)
    try:
        _ = _repo_project(ctx, folder, LONG)
        (repo,) = (r for r in sync_repos(ctx.db, []) if r.name == "w")
        environ = _environ(sandbox, monkeypatch, args)
        session = launch_claude(ctx, env, ClaudeLaunch(cwd=folder, repo_id=repo.id), environ)

        def ended() -> bool:
            row = get_session(ctx.db, session.id)
            pane = pane_of_session(env.tmux, session.id)
            return isinstance(row.state, Exited) and pane is not None and pane.dead

        wait_until("the session to end", ended, timeout=30)
        first = _recorded(args)
        context_file = sandbox.root / "state/meute/sessions" / session.id / "context.md"
        assert first[first.index("--append-system-prompt-file") + 1] == str(context_file)
        assert "--append-system-prompt" not in first
        assert first[-1] == "--name=w"
        assert context_file.read_text(encoding="utf-8").endswith("(w):\n" + LONG.strip())
        assert stat.S_IMODE(context_file.stat().st_mode) == 0o600
        args.unlink()
        project = create_repo_project(ctx.db, "w")
        _ = set_project_instructions(ctx.db, project.id, "short")
        _ = resume_session(ctx, env, session.id, environ)
        return _recorded(args), context_file
    finally:
        ctx.db.close()


def test_a_long_context_reaches_claude_as_a_private_file(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    resumed, _ = _long_to_short(sandbox, monkeypatch)
    assert "--resume" in resumed
    assert resumed[-2].endswith("Project instructions (w):\nshort")


def test_resuming_with_a_short_context_removes_the_stale_file(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    resumed, context_file = _long_to_short(sandbox, monkeypatch)
    assert "--append-system-prompt-file" not in resumed
    assert not context_file.exists()
