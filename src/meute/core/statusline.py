"""Interpretation of the JSON Claude Code pipes to its statusline command."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeGuard


@dataclass(frozen=True, slots=True, kw_only=True)
class StatuslineData:
    """The values of one statusline call; every field is None when absent or unusable."""

    cwd: str | None = None
    model_name: str | None = None
    effort: str | None = None
    context_pct: float | None = None
    five_hour_pct: float | None = None
    five_hour_resets_at: datetime | None = None
    seven_day_pct: float | None = None
    seven_day_resets_at: datetime | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    lines_added: int | None = None
    lines_removed: int | None = None
    worktree_name: str | None = None
    worktree_branch: str | None = None
    worktree_path: str | None = None
    agent_name: str | None = None
    repo_host: str | None = None
    repo_owner: str | None = None
    repo_name: str | None = None


def _is_object_map(node: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(node, Mapping)


def _child(node: object, key: str) -> object:
    return node.get(key) if _is_object_map(node) else None


def _dig(node: object, *path: str) -> object:
    for key in path:
        node = _child(node, key)
    return node


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _first(*values: str | None) -> str | None:
    return next((value for value in values if value is not None), None)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return value


def _integer(value: object) -> int | None:
    return None if isinstance(value, bool) or not isinstance(value, int) else value


def _epoch(value: object) -> datetime | None:
    seconds = _number(value)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def parse_statusline(payload: Mapping[str, object]) -> StatuslineData:
    """Read the statusline JSON `payload`; a missing or mistyped value becomes None.

    Never raises: Claude may change its format at any release.
    """
    five_hour = _child(_child(payload, "rate_limits"), "five_hour")
    seven_day = _child(_child(payload, "rate_limits"), "seven_day")
    return StatuslineData(
        cwd=_first(_text(_dig(payload, "workspace", "current_dir")), _text(_dig(payload, "cwd"))),
        model_name=_first(
            _text(_dig(payload, "model", "display_name")), _text(_dig(payload, "model", "id"))
        ),
        effort=_text(_dig(payload, "effort", "level")),
        context_pct=_number(_dig(payload, "context_window", "used_percentage")),
        five_hour_pct=_number(_child(five_hour, "used_percentage")),
        five_hour_resets_at=_epoch(_child(five_hour, "resets_at")),
        seven_day_pct=_number(_child(seven_day, "used_percentage")),
        seven_day_resets_at=_epoch(_child(seven_day, "resets_at")),
        cost_usd=_number(_dig(payload, "cost", "total_cost_usd")),
        duration_ms=_integer(_dig(payload, "cost", "total_duration_ms")),
        lines_added=_integer(_dig(payload, "cost", "total_lines_added")),
        lines_removed=_integer(_dig(payload, "cost", "total_lines_removed")),
        worktree_name=_text(_dig(payload, "worktree", "name")),
        worktree_branch=_text(_dig(payload, "worktree", "branch")),
        worktree_path=_text(_dig(payload, "worktree", "path")),
        agent_name=_text(_dig(payload, "agent", "name")),
        repo_host=_text(_dig(payload, "workspace", "repo", "host")),
        repo_owner=_text(_dig(payload, "workspace", "repo", "owner")),
        repo_name=_text(_dig(payload, "workspace", "repo", "name")),
    )
