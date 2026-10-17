"""End-to-end tests of `meute config`."""

from pathlib import Path

from conftest import Sandbox

INVALID = "[ui]\nboard_width = = 3\n"


def _config_file(sandbox: Sandbox) -> Path:
    return sandbox.root / "config/meute/config.toml"


def test_set_then_get_round_trips(sandbox: Sandbox) -> None:
    assert sandbox.run("config", "set", "ui.board_width", "72").returncode == 0
    assert sandbox.run("config", "get", "ui.board_width").stdout == "72\n"


def test_set_prints_nothing(sandbox: Sandbox) -> None:
    result = sandbox.run("config", "set", "claude.permission_mode", "plan")
    assert (result.stdout, result.stderr) == ("", "")


def test_set_unknown_key_exits_1(sandbox: Sandbox) -> None:
    result = sandbox.run("config", "set", "ui.nope", "1")
    assert (result.returncode, result.stderr) == (1, "meute: unknown key: ui.nope\n")


def test_path_ends_with_config_toml_even_when_invalid(sandbox: Sandbox) -> None:
    path = _config_file(sandbox)
    path.parent.mkdir(parents=True)
    path.write_text(INVALID, encoding="utf-8")
    result = sandbox.run("config", "path")
    assert result.returncode == 0
    assert result.stdout.endswith("meute/config.toml\n")


def test_set_on_invalid_config_reports_path_and_line_and_keeps_file(sandbox: Sandbox) -> None:
    path = _config_file(sandbox)
    path.parent.mkdir(parents=True)
    path.write_text(INVALID, encoding="utf-8")
    result = sandbox.run("config", "set", "ui.board_width", "72")
    assert result.returncode == 1
    assert "config.toml" in result.stderr
    assert "line 2" in result.stderr
    assert path.read_text(encoding="utf-8") == INVALID
