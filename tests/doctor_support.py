"""Fake `tmux`, `git` and `claude` for `meute doctor` tests, written as `sh` scripts."""

import shutil
import subprocess
from pathlib import Path

from conftest import Sandbox

CLAUDE_HELP = """Usage: claude [options] [command] [prompt]
  --settings <file-or-json>       Load additional settings
  --mcp-config <configs...>       Load MCP servers
  --session-id <uuid>             Use a specific session ID
  -r, --resume [value]            Resume a conversation
  --permission-mode <mode>        Permission mode
  --append-system-prompt <prompt> Append a system prompt
"""
GOOD_TMUX = "tmux 3.5a"
GOOD_GIT = "git version 2.43.0"
GOOD_CLAUDE = "2.1.302 (Claude Code)"
ABSENT = ""  # a tool body meaning: no such tool


def real(name: str) -> str:
    """Return the absolute path of the real `name` (tmux, sleep, ...)."""
    found = shutil.which(name)
    if found is None:
        msg = f"{name} is needed by this test"
        raise RuntimeError(msg)
    return found


def _write(folder: Path, name: str, body: str) -> None:
    script = folder / name
    _ = script.write_bytes(f"#!/bin/sh\n{body}\n".encode("utf-8", errors="surrogateescape"))
    script.chmod(0o755)


def _quoted(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def tmux_script(version: str) -> str:
    """A tmux answering `-V` with `version` and handing the rest to the real tmux.

    So the sandbox's throw-away server is the one queried.
    """
    answer = f'if [ "$1" = -V ]; then printf "%s\\n" {_quoted(version)}; exit 0; fi\n'
    return answer + f'exec {real("tmux")} "$@"'


def print_script(text: str) -> str:
    """A tool printing `text` on one line, whatever its arguments."""
    return f'printf "%s\\n" {_quoted(text)}'


def claude_script(version: str, help_text: str = CLAUDE_HELP) -> str:
    """A claude answering `--version` with `version` and `--help` with `help_text`."""
    return (
        f'case "$1" in --version) printf "%s\\n" {_quoted(version)};;\n'
        f"--help) printf '%s' {_quoted(help_text)};; esac"
    )


def tool_bin(
    tmp_path: Path,
    *,
    tmux: str | None = None,
    git: str | None = None,
    claude: str | None = None,
) -> Path:
    """A `bin` folder holding one `sh` script per tool body given; the defaults are healthy.

    Pass `ABSENT` to leave a tool out.
    """
    folder = tmp_path / "bin"
    folder.mkdir(exist_ok=True)
    bodies = {
        "tmux": tmux_script(GOOD_TMUX) if tmux is None else tmux,
        "git": print_script(GOOD_GIT) if git is None else git,
        "claude": claude_script(GOOD_CLAUDE) if claude is None else claude,
    }
    for name, body in bodies.items():
        if body != ABSENT:
            _write(folder, name, body)
    return folder


def doctor(sandbox: Sandbox, folder: Path) -> subprocess.CompletedProcess[str]:
    """Run `meute doctor` with `folder` as the whole PATH."""
    return sandbox.run("doctor", env={"PATH": str(folder)})


def line(output: str, name: str) -> str:
    """Return the line of `name` without its level and name columns ("" if absent)."""
    for row in output.splitlines():
        if row[6:16].strip() == name:
            return row[16:]
    return ""


def level(output: str, name: str) -> str:
    """Return the level of the line `name` ("" if absent)."""
    for row in output.splitlines():
        if row[6:16].strip() == name:
            return row[:6].strip()
    return ""


def start_server(sandbox: Sandbox, *names: str) -> None:
    """Start the sandbox's throw-away tmux server with one detached session per name."""
    for name in names:
        _ = subprocess.run(
            [
                *(real("tmux"), "-L", sandbox.tmux_socket, "-f", "/dev/null"),
                *("new-session", "-d", "-s", name, real("sleep"), "600"),
            ],
            check=True,
        )


def server_running(sandbox: Sandbox) -> bool:
    """Whether the sandbox's tmux server answers (asking does not start it)."""
    done = subprocess.run(
        [real("tmux"), "-L", sandbox.tmux_socket, "list-sessions"],
        capture_output=True,
        check=False,
    )
    return done.returncode == 0
