"""Reading and writing the configuration file."""

import json
import os
import tempfile
import tomllib
from pathlib import Path
from typing import TypeGuard

from meute.core.config_validate import (
    Config,
    KeysConfig,
    validate_config,
)
from meute.core.errors import ConfigError, InvalidInput

# Config, KeysConfig and validate_config are re-exported for the existing callers.
__all__ = [
    "DEFAULT_CONFIG",
    "Config",
    "KeysConfig",
    "config_get",
    "config_key",
    "ensure_config",
    "load_config",
    "validate_config",
    "write_atomic",
]

DEFAULT_CONFIG = """\
# meute configuration — edit by hand or with `meute config set`.

[repos]
# Folders where meute looks for Git repositories (depth 3).
roots = ["~/git"]

[claude]
# Permission mode of the Claude sessions launched by meute:
# manual, acceptEdits, plan, auto, dontAsk, bypassPermissions.
permission_mode = "manual"
# Minutes without any hook before a running session is shown as stuck?
stuck_after_minutes = 10

[ui]
# Dashboard width, in columns.
board_width = 60
# Below this terminal width, the dashboard goes full screen.
narrow_threshold = 120

[keys]
# Global shortcuts, without the tmux prefix (M- = Alt).
focus_board = "M-p"
focus_main = "M-o"

[quotas]
# Peak hours: weekdays, from peak_start_hour to peak_end_hour, in this time zone.
peak_timezone = "America/New_York"
peak_start_hour = 8
peak_end_hour = 14

[statusline]
# Optional command that receives the same JSON and replaces meute's status line.
chain = ""
"""


def _is_string_tuple(value: object) -> TypeGuard[tuple[str, ...]]:
    if not isinstance(value, tuple):
        return False
    items: tuple[object, ...] = value  # pyright: ignore[reportUnknownVariableType] — isinstance narrows an object to tuple[Unknown, ...]
    return all(isinstance(item, str) for item in items)


def _flatten(config: Config) -> dict[str, object]:
    return {
        "repos.roots": config.repos.roots,
        "claude.permission_mode": config.claude.permission_mode,
        "claude.stuck_after_minutes": config.claude.stuck_after_minutes,
        "ui.board_width": config.ui.board_width,
        "ui.narrow_threshold": config.ui.narrow_threshold,
        "keys.focus_board": config.keys.focus_board,
        "keys.focus_main": config.keys.focus_main,
        "quotas.peak_timezone": config.quotas.peak_timezone,
        "quotas.peak_start_hour": config.quotas.peak_start_hour,
        "quotas.peak_end_hour": config.quotas.peak_end_hour,
        "statusline.chain": config.statusline.chain,
    }


_KEYS = frozenset(_flatten(Config()))


def config_key(key: str) -> tuple[str, str]:
    """Split a key such as `ui.board_width` into its section and field names.

    Raises:
        InvalidInput: the key is not a field of Config.
    """
    if key not in _KEYS:
        message = f"unknown key: {key}"
        raise InvalidInput(message)
    section, _, name = key.partition(".")
    return section, name


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` through a temporary file in the same folder, creating parents.

    A symbolic link is followed (even a dangling one), so the link itself survives.
    """
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
        try:
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path.replace(path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise


def ensure_config(path: Path) -> bool:
    """Write the default configuration if `path` does not exist; return whether it did."""
    if path.exists():
        return False
    write_atomic(path, DEFAULT_CONFIG)
    return True


def load_config(path: Path) -> Config:
    """Read the configuration at `path`; an absent file yields the defaults.

    Raises:
        ConfigError: the file is not valid TOML or holds an invalid value.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return Config()
    try:
        return validate_config(tomllib.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, InvalidInput) as error:
        raise ConfigError(path, str(error)) from error


def config_get(path: Path, key: str) -> str:
    """Return the value of `key` as text: the file's value, else the default.

    Raises:
        InvalidInput: the key is unknown.
        ConfigError: the file is invalid.
    """
    config_key(key)
    value = _flatten(load_config(path))[key]
    if _is_string_tuple(value):
        return json.dumps(list(value), ensure_ascii=False)
    return str(value)
