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
