"""End-to-end tests of Claude sessions launched by `meute session new`, with a fake `claude`."""

import os
import shutil
import stat
import sys
from pathlib import Path

from conftest import Sandbox
from meute.core.db.sessions import list_sessions
from meute.core.session import AgentKind
from meute.core.session_state import Unknown
from support import load_json, wait_until

_NO_CLAUDE = (
    "meute: claude not found: Claude sessions are disabled;"
    " Bash sessions remain available with --kind bash\n"
)


def _fake_claude(sandbox: Sandbox) -> tuple[dict[str, str], Path]:
    """A `claude` that records its arguments, one per line, then sleeps; and a PATH with it."""
    bin_dir = sandbox.root / "fakebin"
    bin_dir.mkdir()
    record = sandbox.root / "argv.txt"
    script = bin_dir / "claude"
    script.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > {record}\nexec sleep 3600\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return {"PATH": f"{bin_dir}:{os.environ['PATH']}"}, record


def _folder(sandbox: Sandbox) -> Path:
    folder = (sandbox.root / "w").resolve()
    folder.mkdir()
    return folder


def _argv(record: Path) -> list[str]:
    wait_until("the fake claude to start", record.exists)
    return record.read_text(encoding="utf-8").splitlines()


def test_new_defaults_to_claude_with_explicit_permission_mode(sandbox: Sandbox) -> None:
    env, record = _fake_claude(sandbox)
    folder = _folder(sandbox)
    result = sandbox.run("session", "new", "--cwd", str(folder), "--title", "trial", env=env)
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (session,) = list_sessions(db)
    assert (session.agent, session.state, session.title) == (AgentKind.CLAUDE, Unknown(), "trial")
    settings = sandbox.root / "state/meute/sessions" / session.id / "settings.json"
    assert _argv(record) == [
        "--settings",
        str(settings),
        "--mcp-config",
        str(settings.with_name("mcp.json")),
        "--session-id",
        session.id,
        "--permission-mode",
        "auto",
        "--name=trial",
    ]
    assert stat.S_IMODE(settings.stat().st_mode) == 0o600
    panes = sandbox.tmux().run("list-panes", "-a", "-F", "#{session_name} #{@meute_id}")
    assert f"meute-bg {session.id}" in panes.splitlines()


def test_permission_mode_option_wins(sandbox: Sandbox) -> None:
    env, record = _fake_claude(sandbox)
    folder = _folder(sandbox)
    args = ("session", "new", "--cwd", str(folder), "--permission-mode", "plan")
    assert sandbox.run(*args, env=env).returncode == 0
    argv = _argv(record)
    assert argv[argv.index("--permission-mode") + 1] == "plan"


def test_unknown_permission_mode_is_refused(sandbox: Sandbox) -> None:
    env, _ = _fake_claude(sandbox)
    folder = _folder(sandbox)
    args = ("session", "new", "--cwd", str(folder), "--permission-mode", "yolo")
    result = sandbox.run(*args, env=env)
    assert (result.returncode, result.stderr) == (1, "meute: unknown permission mode: yolo\n")
    with sandbox.db() as db:
        assert list_sessions(db) == []


def test_permission_mode_with_bash_is_refused(sandbox: Sandbox) -> None:
    folder = _folder(sandbox)
    args = ("session", "new", "--kind", "bash", "--cwd", str(folder), "--permission-mode", "plan")
    result = sandbox.run(*args)
    assert (result.returncode, result.stderr) == (
        1,
        "meute: --permission-mode only applies to Claude sessions\n",
    )
    assert not sandbox.tmux().is_running()


def test_missing_claude_fails_clearly_and_bash_still_works(sandbox: Sandbox) -> None:
    folder = _folder(sandbox)
    tmux_dir = str(Path(shutil.which("tmux") or "").parent)
    env = {"PATH": f"{Path(sys.executable).parent}:{tmux_dir}"}
    result = sandbox.run("session", "new", "--cwd", str(folder), env=env)
    assert (result.returncode, result.stderr) == (1, _NO_CLAUDE)
    with sandbox.db() as db:
        assert list_sessions(db) == []
    assert not (sandbox.root / "state/meute/sessions").exists()
    bash = sandbox.run("session", "new", "--kind", "bash", "--cwd", str(folder), env=env)
    assert bash.returncode == 0, bash.stderr


def test_missing_folder_is_reported_before_claude(sandbox: Sandbox) -> None:
    missing = sandbox.root / "nope"
    result = sandbox.run("session", "new", "--cwd", str(missing))
    assert result.stderr == f"meute: folder not found: {missing}\n"


def test_session_list_shows_permission_mode_and_json_has_claude_key(sandbox: Sandbox) -> None:
    env, record = _fake_claude(sandbox)
    folder = _folder(sandbox)
    args = ("session", "new", "--cwd", str(folder), "--title", "trial", "--permission-mode", "auto")
    assert sandbox.run(*args, env=env).returncode == 0
    _ = _argv(record)
    listed = sandbox.run("session", "list", env=env)
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.rstrip("\n").endswith("  [auto]"), listed.stdout
    payload = load_json(sandbox.run("session", "list", "--json", env=env).stdout)
    assert isinstance(payload, dict)
    sessions = payload["sessions"]
    assert isinstance(sessions, list)
    first = sessions[0]
    assert isinstance(first, dict)
    claude = first["claude"]
    assert isinstance(claude, dict)
    assert claude["permission_mode"] == "auto"
