"""The configuration model and the validation of parsed TOML into it."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypeGuard
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from meute.core.errors import InvalidInput

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

    permission_mode: str = "auto"
    stuck_after_minutes: int = 10


@dataclass(frozen=True, slots=True, kw_only=True)
class UiConfig:
    """Dashboard layout."""

    board_width: int = 60
    narrow_threshold: int = 120
    show_details: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class KeysConfig:
    """Global tmux shortcuts, as tmux key names."""

    focus_board: str = "M-p"
    focus_main: str = "M-o"


@dataclass(frozen=True, slots=True, kw_only=True)
class QuotasConfig:
    """Peak hours of the Claude quotas."""

    peak_timezone: str = "America/New_York"
    peak_start_hour: int = 8
    peak_end_hour: int = 14


@dataclass(frozen=True, slots=True, kw_only=True)
class StatuslineConfig:
    """The status line meute prints for Claude Code."""

    chain: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    """The whole configuration; every field has a default."""

    repos: ReposConfig = field(default_factory=ReposConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    keys: KeysConfig = field(default_factory=KeysConfig)
    quotas: QuotasConfig = field(default_factory=QuotasConfig)
    statusline: StatuslineConfig = field(default_factory=StatuslineConfig)


def _is_table(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_string_list(value: object) -> TypeGuard[list[str]]:
    if not isinstance(value, list):
        return False
    items: list[object] = value  # pyright: ignore[reportUnknownVariableType] — isinstance narrows an object to list[Unknown]
    return all(isinstance(item, str) for item in items)


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


def _bool(section: Mapping[str, object], dotted: str, *, default: bool) -> bool:
    value = section.get(dotted.partition(".")[2], default)
    if not isinstance(value, bool):
        message = f"{dotted}: expected true or false"
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
    value = section.get("permission_mode", "auto")
    if not isinstance(value, str) or value not in PERMISSION_MODES:
        message = f"claude.permission_mode: expected one of {', '.join(sorted(PERMISSION_MODES))}"
        raise InvalidInput(message)
    return value


_TMUX_KEY = re.compile(r"[A-Za-z0-9-]{1,20}")


def _key(section: Mapping[str, object], name: str, default: str) -> str:
    """Return a tmux key name; it is copied into the generated tmux file, so it is strict."""
    value = section.get(name, default)
    if not isinstance(value, str) or _TMUX_KEY.fullmatch(value) is None:
        message = f"keys.{name}: expected a tmux key such as M-p"
        raise InvalidInput(message)
    return value


def _timezone(section: Mapping[str, object]) -> str:
    value = section.get("peak_timezone", "America/New_York")
    message = "quotas.peak_timezone: expected an IANA time zone name"
    if not isinstance(value, str):
        raise InvalidInput(message)
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise InvalidInput(message) from None
    return value


def _chain(section: Mapping[str, object]) -> str:
    value = section.get("chain", "")
    if not isinstance(value, str):
        message = "statusline.chain: expected a command as a string"
        raise InvalidInput(message)
    return value


def validate_config(data: Mapping[str, object]) -> Config:
    """Turn parsed TOML into a Config, ignoring unknown sections and keys.

    Raises:
        InvalidInput: a known key holds a value of the wrong type or range.
    """
    claude = _section(data, "claude")
    ui = _section(data, "ui")
    keys = _section(data, "keys")
    quotas = _section(data, "quotas")
    statusline = _section(data, "statusline")
    default_keys = KeysConfig()
    return Config(
        repos=ReposConfig(roots=_roots(_section(data, "repos"))),
        claude=ClaudeConfig(
            permission_mode=_permission_mode(claude),
            stuck_after_minutes=_int(claude, "claude.stuck_after_minutes", 10, 1),
        ),
        ui=UiConfig(
            board_width=_int(ui, "ui.board_width", 60, 1),
            narrow_threshold=_int(ui, "ui.narrow_threshold", 120, 1),
            show_details=_bool(ui, "ui.show_details", default=True),
        ),
        keys=KeysConfig(
            focus_board=_key(keys, "focus_board", default_keys.focus_board),
            focus_main=_key(keys, "focus_main", default_keys.focus_main),
        ),
        quotas=QuotasConfig(
            peak_timezone=_timezone(quotas),
            peak_start_hour=_int(quotas, "quotas.peak_start_hour", 8, 0, 24),
            peak_end_hour=_int(quotas, "quotas.peak_end_hour", 14, 0, 24),
        ),
        statusline=StatuslineConfig(chain=_chain(statusline)),
    )
