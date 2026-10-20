"""`M-t` in the generated tmux configuration: the line, the key setting and real popups."""

import time
from pathlib import Path

import pytest

from meute.cli.context import CliContext
from meute.cli.tmux_env import open_tmux_env
from meute.core.config import DEFAULT_CONFIG, Config, KeysConfig, config_get, load_config
from meute.core.errors import ConfigError
from meute.tmux.conf import Keys, LayoutSpec, render_config
from support import wait_until
from test_cli_task_quick import ctx  # noqa: F401 — fixture reused  # pyright: ignore[reportUnusedImport] — fixture reused
from test_tmux_format_literal import INJECTION, arm_marker, settle
from tmux_support import TestServer, attached_client

SLEEP = ("sh", "-c", "sleep 3600")
MEUTE = ("/opt/meute/bin/python", "-m", "meute")


def _spec(command: tuple[str, ...] = MEUTE, key: str = "M-t") -> LayoutSpec:
    return LayoutSpec(
        board_width=60,
        narrow_threshold=120,
        board_command=SLEEP,
        welcome_command=SLEEP,
        sync_command=("true",),
        attention_command=command,
        keys=Keys(focus_board="M-p", focus_main="M-o", quick_task=key),
    )


def _binding(text: str, key: str) -> str:
    (line,) = (line for line in text.splitlines() if line.startswith(f"bind -n {key} "))
    return line


def _popup(width: str) -> str:
    """The popup command of the brief, escaped once more for the `if-shell` around it."""
    command = r"'/opt/meute/bin/python' '-m' 'meute' 'task' 'quick'"
    return rf"display-popup -B -E -w {width} -h 12 -T \"\" \"{command}\""


def test_quick_task_line() -> None:
    assert _binding(render_config(_spec()), "M-t") == (
        'bind -n M-t if-shell -F "#{e|<:#{client_width},76}"'
        f' "{_popup("100%")}" "{_popup("76")}"'
    )


def test_quick_task_line_follows_the_configured_key() -> None:
    line = _binding(render_config(_spec(key="M-T")), "M-T")
    assert line.startswith("bind -n M-T if-shell -F ")
    assert "M-t" not in render_config(_spec(key="M-T"))


def test_quick_task_binding_is_omitted_without_a_command() -> None:
    assert "display-popup" not in render_config(_spec(command=()))


def test_the_key_setting_defaults_to_m_t_and_is_documented(tmp_path: Path) -> None:
    assert KeysConfig().quick_task == "M-t"
    assert '# Quick task from anywhere.\nquick_task = "M-t"\n' in DEFAULT_CONFIG
    path = tmp_path / "config.toml"
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    assert config_get(path, "keys.quick_task") == "M-t"


def test_the_key_setting_is_configurable(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[keys]\nquick_task = 'M-T'\n", encoding="utf-8")
    assert load_config(path).keys.quick_task == "M-T"


@pytest.mark.parametrize("value", ["M-t;x", r"M-t \; kill-server", "", "a" * 21])
def test_the_key_setting_must_be_a_tmux_key(tmp_path: Path, value: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f"[keys]\nquick_task = '{value}'\n", encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        _ = load_config(path)
    assert str(info.value).endswith("keys.quick_task: expected a tmux key such as M-p")


def test_the_tmux_environment_binds_the_configured_key(ctx: CliContext) -> None:  # noqa: F811 — fixture
    configured = CliContext(
        db=ctx.db,
        now=ctx.now,
        actor=ctx.actor,
        config=Config(keys=KeysConfig(quick_task="M-T")),
        paths=ctx.paths,
    )
    env = open_tmux_env(configured, {})
    assert env.spec.keys.quick_task == "M-T"
    assert "bind -n M-T if-shell" in env.config_file.read_text(encoding="utf-8")


def _recorder(folder: Path, *, linger: float = 0) -> Path:
    """A fake meute that appends its argv, NUL-separated, to `$OUT`, then lingers."""
    folder.mkdir()
    script = folder / "python"
    script.write_text(f'#!/bin/sh\nprintf \'%s\\0\' "$0" "$@" >> "$OUT"\nsleep {linger}\n')
    script.chmod(0o755)
    return script


def _install(server: TestServer, tmp_path: Path, script: Path) -> Path:
    out = tmp_path / "argv"
    server.tmux.run("set-environment", "-g", "OUT", str(out))
    conf = tmp_path / "tmux.conf"
    conf.write_text(render_config(_spec((str(script), "-m", "meute"))))
    server.tmux.run("source-file", str(conf))
    return out


def _runs(out: Path) -> list[list[str]]:
    if not out.exists():
        return []
    words = out.read_text().split("\0")[:-1]
    return [words[i : i + 5] for i in range(0, len(words), 5)]


@pytest.mark.parametrize("columns", [100, 76, 60])
def test_m_t_opens_the_popup_with_the_intended_argv(
    tmux_server: TestServer, tmp_path: Path, columns: int
) -> None:
    marker = arm_marker(tmux_server.tmux, tmp_path)
    script = _recorder(tmp_path / f"my app's #1 {INJECTION} \\ $HOME")
    out = _install(tmux_server, tmp_path, script)
    with attached_client(tmux_server, columns=columns) as client:
        tmux_server.tmux.run("send-keys", "-K", "-c", client, "M-t")
        wait_until("the popup command", lambda: bool(_runs(out)))
    settle(tmux_server.tmux, tmp_path)
    assert _runs(out) == [[str(script), "-m", "meute", "task", "quick"]]
    assert not marker.exists()


def test_a_second_m_t_opens_no_second_window(tmux_server: TestServer, tmp_path: Path) -> None:
    script = _recorder(tmp_path / "bin", linger=2)
    out = _install(tmux_server, tmp_path, script)
    with attached_client(tmux_server, columns=100) as client:
        tmux_server.tmux.run("send-keys", "-K", "-c", client, "M-t")
        wait_until("the popup command", lambda: bool(_runs(out)))
        # The key reaches the open window, not tmux; a popup asked for meanwhile is refused
        # without a word (the command succeeds, nothing runs).
        tmux_server.tmux.run("send-keys", "-K", "-c", client, "M-t")
        tmux_server.tmux.run("display-popup", "-c", client, "-E", f"touch {tmp_path}/second")
        assert (
            tmux_server.tmux.run("display-message", "-p", "-c", client, "#{client_message}") == ""
        )
        time.sleep(2.5)
    assert len(_runs(out)) == 1
    assert not (tmp_path / "second").exists()
