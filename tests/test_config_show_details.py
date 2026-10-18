"""`ui.show_details`."""

from pathlib import Path

import pytest

from meute.cli.config_edit import config_set
from meute.core.config import DEFAULT_CONFIG, Config, config_get, load_config
from meute.core.errors import ConfigError, InvalidInput


def _load(tmp_path: Path, text: str) -> Config:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return load_config(path)


def test_default_is_true_and_documented() -> None:
    assert Config().ui.show_details is True
    assert (
        "# Show the details of the selected session under the list.\nshow_details = true\n"
    ) in DEFAULT_CONFIG


def test_value_is_read(tmp_path: Path) -> None:
    assert _load(tmp_path, "[ui]\nshow_details = false\n").ui.show_details is False


@pytest.mark.parametrize("value", ['"no"', "0", "1", "[]"])
def test_non_booleans_are_refused(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match=r"ui\.show_details: expected true or false$"):
        _ = _load(tmp_path, f"[ui]\nshow_details = {value}\n")


def test_get_and_set_speak_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    assert config_get(path, "ui.show_details") == "true"
    config_set(path, "ui.show_details", "false")
    assert config_get(path, "ui.show_details") == "false"
    with pytest.raises(InvalidInput, match=r"^ui\.show_details: expected true or false$"):
        config_set(path, "ui.show_details", "maybe")
