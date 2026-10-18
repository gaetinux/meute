"""Tests for the claude command line."""

from pathlib import Path

import pytest

from meute.claude.launch import claude_argv, find_claude
from meute.core.errors import InvalidInput
from meute.core.session import SessionId

SID = SessionId("0b6f1d0e-0000-4000-8000-000000000003")


def test_argv_exact() -> None:
    argv = claude_argv(
        claude=Path("/bin/claude"),
        settings=Path("/s/settings.json"),
        session_id=SID,
        permission_mode="plan",
        title="Fix it",
    )
    assert argv == (
        "/bin/claude", "--settings", "/s/settings.json", "--session-id", SID,
        "--permission-mode", "plan", "--name=Fix it",
    )  # fmt: skip


def test_title_starting_with_dash_stays_one_argument() -> None:
    argv = claude_argv(
        claude=Path("c"), settings=Path("s"), session_id=SID,
        permission_mode="auto", title="--dangerous",
    )  # fmt: skip
    assert argv[-1] == "--name=--dangerous"


def test_unknown_permission_mode() -> None:
    with pytest.raises(InvalidInput, match=r"^unknown permission mode: yolo$"):
        claude_argv(
            claude=Path("c"), settings=Path("s"), session_id=SID,
            permission_mode="yolo", title="t",
        )  # fmt: skip


def test_find_claude(tmp_path: Path) -> None:
    binary = tmp_path / "claude"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    assert find_claude({"PATH": str(tmp_path)}) == binary
    assert find_claude({"PATH": str(tmp_path / "none")}) is None
