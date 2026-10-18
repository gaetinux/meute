"""`claude.stuck_after_minutes`."""

from pathlib import Path

import pytest

from meute.core.config import DEFAULT_CONFIG, Config, load_config
from meute.core.errors import ConfigError


def _load(tmp_path: Path, text: str) -> Config:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return load_config(path)


def test_default_is_ten_minutes_and_documented() -> None:
    assert Config().claude.stuck_after_minutes == 10
    assert (
        "# Minutes without any hook before a running session is shown as stuck?\n"
        "stuck_after_minutes = 10\n"
    ) in DEFAULT_CONFIG


def test_value_is_read(tmp_path: Path) -> None:
    assert _load(tmp_path, "[claude]\nstuck_after_minutes = 3\n").claude.stuck_after_minutes == 3


@pytest.mark.parametrize("value", ["0", "-1", '"ten"', "true", "1.5"])
def test_invalid_values_are_refused(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match=r"claude\.stuck_after_minutes: expected an integer >= 1"):
        _ = _load(tmp_path, f"[claude]\nstuck_after_minutes = {value}\n")
