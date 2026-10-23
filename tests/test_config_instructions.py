"""`claude.instructions` in the configuration."""

import tomllib

import pytest

from conftest import Sandbox
from meute.core.config import DEFAULT_CONFIG
from meute.core.config_validate import ClaudeConfig, validate_config
from meute.core.errors import InvalidInput


def test_default_config_has_the_key_and_is_valid() -> None:
    assert (
        '# Instructions added to every Claude session launched by meute.\ninstructions = ""\n'
    ) in DEFAULT_CONFIG
    assert validate_config(tomllib.loads(DEFAULT_CONFIG)).claude.instructions == ""
    assert ClaudeConfig().instructions == ""


def test_instructions_must_be_a_string() -> None:
    with pytest.raises(InvalidInput, match=r"claude\.instructions"):
        validate_config({"claude": {"instructions": 3}})


def test_set_then_get(sandbox: Sandbox) -> None:
    assert sandbox.run("config", "set", "claude.instructions", "x").returncode == 0
    assert sandbox.run("config", "get", "claude.instructions").stdout == "x\n"


@pytest.mark.parametrize("char", ["\x00", "\x01", "\x1b", "\r", "\x1f"])
def test_instructions_refuse_control_characters(char: str) -> None:
    with pytest.raises(
        InvalidInput, match=r"^claude\.instructions: instructions contain a control character$"
    ):
        validate_config({"claude": {"instructions": f"a{char}b"}})


def test_instructions_keep_newlines_and_tabs() -> None:
    config = validate_config({"claude": {"instructions": "a\n\tb\x7fé"}})
    assert config.claude.instructions == "a\n\tb\x7fé"


def test_a_nul_in_the_configuration_file_is_a_config_error(sandbox: Sandbox) -> None:
    config = sandbox.root / "config/meute/config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('[claude]\ninstructions = "a\\u0000b"\n', encoding="utf-8")
    result = sandbox.run("config", "get", "claude.instructions")
    assert result.returncode != 0
    assert "instructions contain a control character" in result.stderr


def test_config_set_refuses_a_control_character(sandbox: Sandbox) -> None:
    result = sandbox.run("config", "set", "claude.instructions", "a\x1bb")
    assert result.returncode != 0
    assert "instructions contain a control character" in result.stderr
    assert sandbox.run("config", "get", "claude.instructions").stdout == "\n"
