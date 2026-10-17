"""Reading and validating the configuration file."""

import json
import os
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeGuard
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from meute.core.errors import ConfigError, InvalidInput

DEFAULT_CONFIG = """\
# meute configuration — edit by hand or with `meute config set`.

[repos]
# Folders where meute looks for Git repositories (depth 3).
roots = ["~/git"]

[claude]
# Permission mode of the Claude sessions launched by meute:
# manual, acceptEdits, plan, auto, dontAsk, bypassPermissions.
permission_mode = "manual"

[ui]
# Dashboard width, in columns.
board_width = 60
# Below this terminal width, the dashboard goes full screen.
narrow_threshold = 120

[quotas]
# Peak hours: weekdays, from peak_start_hour to peak_end_hour, in this time zone.
peak_timezone = "America/New_York"
peak_start_hour = 8
peak_end_hour = 14
"""

PERMISSION_MODES = frozenset(
    {"manual", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"}
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ReposConfig:
    """Where to look for Git repositories."""

    roots: tuple[str, ...] = ("~/git",)


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaudeConfig:
    """How Claude sessions are launched."""

    permission_mode: str = "manual"


@dataclass(frozen=True, slots=True, kw_only=True)
class UiConfig:
    """Dashboard layout."""

    board_width: int = 60
    narrow_threshold: int = 120


@dataclass(frozen=True, slots=True, kw_only=True)
class QuotasConfig:
    """Peak hours of the Claude quotas."""

    peak_timezone: str = "America/New_York"
    peak_start_hour: int = 8
    peak_end_hour: int = 14


@dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    """The whole configuration; every field has a default."""

    repos: ReposConfig = field(default_factory=ReposConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    quotas: QuotasConfig = field(default_factory=QuotasConfig)


def _is_table(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_string_list(value: object) -> TypeGuard[list[str]]:
    if not isinstance(value, list):
        return False
    items: list[object] = value  # pyright: ignore[reportUnknownVariableType] — isinstance narrows an object to list[Unknown]
    return all(isinstance(item, str) for item in items)


def _is_string_tuple(value: object) -> TypeGuard[tuple[str, ...]]:
    return isinstance(value, tuple)


def _section(data: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = data.get(name, {})
    if not _is_table(value):
        message = f"{name}: expected a table"
        raise InvalidInput(message)
    return value


def _int(
    section: Mapping[str, object], dotted: str, default: int, low: int, high: int | None = None
) -> int:
    value = section.get(dotted.partition(".")[2], default)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < low
        or (high is not None and value > high)
    ):
        expected = (
            f"an integer >= {low}" if high is None else f"an integer between {low} and {high}"
        )
        message = f"{dotted}: expected {expected}"
        raise InvalidInput(message)
    return value


def _roots(section: Mapping[str, object]) -> tuple[str, ...]:
    value = section.get("roots")
    if value is None:
        return ReposConfig().roots
    if not _is_string_list(value):
        message = "repos.roots: expected a list of strings"
        raise InvalidInput(message)
    return tuple(value)


def _permission_mode(section: Mapping[str, object]) -> str:
    value = section.get("permission_mode", "manual")
    if not isinstance(value, str) or value not in PERMISSION_MODES:
        message = f"claude.permission_mode: expected one of {', '.join(sorted(PERMISSION_MODES))}"
        raise InvalidInput(message)
    return value


def _timezone(section: Mapping[str, object]) -> str:
    value = section.get("peak_timezone", "America/New_York")
    try:
        if isinstance(value, str):
            ZoneInfo(value)
            return value
    except (ZoneInfoNotFoundError, ValueError, OSError):
        pass
    message = "quotas.peak_timezone: expected an IANA time zone name"
    raise InvalidInput(message)


def validate_config(data: Mapping[str, object]) -> Config:
    """Turn parsed TOML into a Config, ignoring unknown sections and keys.

    Raises:
        InvalidInput: a known key holds a value of the wrong type or range.
    """
    ui = _section(data, "ui")
    quotas = _section(data, "quotas")
    return Config(
        repos=ReposConfig(roots=_roots(_section(data, "repos"))),
        claude=ClaudeConfig(permission_mode=_permission_mode(_section(data, "claude"))),
        ui=UiConfig(
            board_width=_int(ui, "ui.board_width", 60, 1),
            narrow_threshold=_int(ui, "ui.narrow_threshold", 120, 1),
        ),
        quotas=QuotasConfig(
            peak_timezone=_timezone(quotas),
            peak_start_hour=_int(quotas, "quotas.peak_start_hour", 8, 0, 24),
            peak_end_hour=_int(quotas, "quotas.peak_end_hour", 14, 0, 24),
        ),
    )


def _flatten(config: Config) -> dict[str, object]:
    return {
        "repos.roots": config.repos.roots,
        "claude.permission_mode": config.claude.permission_mode,
        "ui.board_width": config.ui.board_width,
        "ui.narrow_threshold": config.ui.narrow_threshold,
        "quotas.peak_timezone": config.quotas.peak_timezone,
        "quotas.peak_start_hour": config.quotas.peak_start_hour,
        "quotas.peak_end_hour": config.quotas.peak_end_hour,
    }


def config_key(key: str) -> tuple[str, str]:
    """Split a key such as `ui.board_width` into its section and field names.

    Raises:
        InvalidInput: the key is not a field of Config.
    """
    if key not in _flatten(Config()):
        message = f"unknown key: {key}"
        raise InvalidInput(message)
    section, _, name = key.partition(".")
    return section, name


def write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` through a temporary file in the same folder, creating parents."""
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
