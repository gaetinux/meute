"""End-to-end tests of `meute doctor`: the tools, the timeout and the exit code."""

import os
import signal
import time
from contextlib import suppress
from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from conftest import Sandbox
from doctor_support import (
    ABSENT,
    CLAUDE_HELP,
    GOOD_CLAUDE,
    claude_script,
    doctor,
    level,
    line,
    print_script,
    real,
    server_running,
    start_server,
    tmux_script,
    tool_bin,
)


def test_everything_fine(sandbox: Sandbox, tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    assert sandbox.run("task", "list").returncode == 0  # creates the configuration and database
    start_server(sandbox, "one")
    result = doctor(sandbox, tool_bin(tmp_path))
    assert result.returncode == 0, result.stderr
    shown = result.stdout.replace(str(sandbox.root), "<root>")
    assert shown.replace(sandbox.tmux_socket, "<socket>") == snapshot


def test_tmux_absent_fails_and_skips_the_server_line(sandbox: Sandbox, tmp_path: Path) -> None:
    result = doctor(sandbox, tool_bin(tmp_path, tmux=ABSENT))
    assert line(result.stdout, "tmux") == "not found: meute needs tmux 3.2 or later"
    assert level(result.stdout, "tmux") == "fail"
    assert level(result.stdout, "server") == ""
    assert result.returncode == 1


def test_tmux_too_old_fails_and_skips_the_server_line(sandbox: Sandbox, tmp_path: Path) -> None:
    result = doctor(sandbox, tool_bin(tmp_path, tmux=tmux_script("tmux 3.1c")))
    assert line(result.stdout, "tmux") == "3.1c: meute needs tmux 3.2 or later"
    assert level(result.stdout, "server") == ""
    assert result.returncode == 1


def test_tmux_unreadable_fails(sandbox: Sandbox, tmp_path: Path) -> None:
    result = doctor(sandbox, tool_bin(tmp_path, tmux=tmux_script("tmux next")))
    assert line(result.stdout, "tmux") == "unreadable version: tmux next"
    assert level(result.stdout, "tmux") == "fail"


def test_tmux_3_2_warns_with_exit_code_0(sandbox: Sandbox, tmp_path: Path) -> None:
    result = doctor(sandbox, tool_bin(tmp_path, tmux=tmux_script("tmux 3.2a")))
    assert line(result.stdout, "tmux") == "3.2a: M-t needs tmux 3.3 or later"
    assert level(result.stdout, "tmux") == "warn"
    assert "fail" not in [row[:6].strip() for row in result.stdout.splitlines()]
    assert result.returncode == 0, result.stdout


def test_git_absent_too_old_and_unreadable(sandbox: Sandbox, tmp_path: Path) -> None:
    need = "worktrees and the Git line need git 2.36 or later"
    cases = {
        ABSENT: f"not found: {need}",
        print_script("git version 2.35.1"): f"2.35.1: {need}",
        print_script("git: what?"): "unreadable version: git: what?",
    }
    for body, expected in cases.items():
        (tmp_path / "bin/git").unlink(missing_ok=True)
        result = doctor(sandbox, tool_bin(tmp_path, git=body))
        assert line(result.stdout, "git") == expected
        assert level(result.stdout, "git") == "fail"
        assert result.returncode == 1


def test_claude_absent_fails_and_skips_the_options_line(sandbox: Sandbox, tmp_path: Path) -> None:
    result = doctor(sandbox, tool_bin(tmp_path, claude=ABSENT))
    assert line(result.stdout, "claude") == "not found: Claude sessions are disabled"
    assert level(result.stdout, "claude") == "fail"
    assert level(result.stdout, "options") == ""
    assert result.returncode == 1


def test_claude_too_old_and_unreadable_warn(sandbox: Sandbox, tmp_path: Path) -> None:
    cases = {
        "2.1.300 (Claude Code)": (
            "2.1.300 (Claude Code): meute is tested with claude 2.1.301 or later"
        ),
        "Claude Code": "unreadable version: Claude Code",
    }
    for version, expected in cases.items():
        result = doctor(sandbox, tool_bin(tmp_path, claude=claude_script(version)))
        assert line(result.stdout, "claude") == expected
        assert level(result.stdout, "claude") == "warn"
        assert level(result.stdout, "options") == "ok"


def test_options_missing_are_listed_as_whole_words(sandbox: Sandbox, tmp_path: Path) -> None:
    help_text = CLAUDE_HELP.replace("--append-system-prompt ", "--append-system-prompt-file ")
    help_text = help_text.replace("--resume", "--resumed")
    result = doctor(sandbox, tool_bin(tmp_path, claude=claude_script(GOOD_CLAUDE, help_text)))
    expected = "claude --help does not list: --resume, --append-system-prompt"
    assert line(result.stdout, "options") == expected
    assert level(result.stdout, "options") == "fail"


def test_options_fine(sandbox: Sandbox, tmp_path: Path) -> None:
    result = doctor(sandbox, tool_bin(tmp_path))
    assert line(result.stdout, "options") == "claude --help lists every option meute uses"


def test_a_mute_claude_help_times_out_after_5_seconds(sandbox: Sandbox, tmp_path: Path) -> None:
    body = f'case "$1" in --version) echo "{GOOD_CLAUDE}";; --help) {real("sleep")} 10;; esac'
    started = time.monotonic()
    result = doctor(sandbox, tool_bin(tmp_path, claude=body))
    elapsed = time.monotonic() - started
    assert line(result.stdout, "options") == "claude did not answer within 5 s"
    assert level(result.stdout, "options") == "fail"
    assert elapsed < 8
    assert result.returncode == 1


def test_a_grandchild_escaping_the_group_does_not_hang_doctor(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    pid_file = tmp_path / "escaped.pid"
    escape = f"{real('setsid')} {real('sleep')} 20 & echo $! > {pid_file}; wait"
    body = f'case "$1" in --version) echo "{GOOD_CLAUDE}";; --help) {escape};; esac'
    started = time.monotonic()
    try:
        result = doctor(sandbox, tool_bin(tmp_path, claude=body))
        elapsed = time.monotonic() - started
    finally:
        with suppress(OSError, ValueError):
            os.kill(int(pid_file.read_text()), signal.SIGKILL)
    assert line(result.stdout, "options") == "claude did not answer within 5 s"
    assert elapsed < 9


def test_escape_sequences_and_bad_bytes_are_neutralised(sandbox: Sandbox, tmp_path: Path) -> None:
    body = r"printf '\033[2Jgit version 2.40\377\n'"
    result = doctor(sandbox, tool_bin(tmp_path, git=body))
    assert "\x1b" not in result.stdout
    assert "Traceback" not in result.stderr
    assert line(result.stdout, "git") == "\ufffd[2Jgit version 2.40\ufffd"
    assert level(result.stdout, "git") == "ok"


def test_server_stopped_and_running(sandbox: Sandbox, tmp_path: Path) -> None:
    folder = tool_bin(tmp_path)
    stopped = doctor(sandbox, folder)
    expected = f"tmux server {sandbox.tmux_socket}: not running (meute starts it)"
    assert line(stopped.stdout, "server") == expected
    assert level(stopped.stdout, "server") == "ok"
    start_server(sandbox, "one", "two")
    running = doctor(sandbox, folder)
    assert (
        line(running.stdout, "server") == f"tmux server {sandbox.tmux_socket}: running, 2 sessions"
    )


def test_a_fresh_sandbox_stays_empty(sandbox: Sandbox, tmp_path: Path) -> None:
    result = doctor(sandbox, tool_bin(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    for folder in ("config/meute", "data/meute", "state/meute"):
        assert not (sandbox.root / folder).exists(), folder
    assert not server_running(sandbox)
    config = sandbox.root / "config/meute/config.toml"
    assert line(result.stdout, "config") == f"{config} (absent: defaults are used)"
    database = sandbox.root / "data/meute/meute.db"
    assert line(result.stdout, "database") == f"{database}: created at the first start"
    assert line(result.stdout, "state") == str(sandbox.root / "state/meute")
    assert level(result.stdout, "note") == "note"
    assert result.stdout.rstrip("\n").endswith("1 problem found")
