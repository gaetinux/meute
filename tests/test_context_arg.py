"""The choice between an argv word and a private file for the composed context."""

import stat
from pathlib import Path

from meute.claude.context_arg import (
    CONTEXT_ARGV_LIMIT,
    ContextFile,
    ContextText,
    prepare_context,
)
from meute.claude.launch import claude_argv
from meute.core.session import SessionId

SID = SessionId("0b6f1d0e-0000-4000-8000-000000000003")


def test_exactly_the_limit_stays_in_argv_and_one_more_byte_goes_to_a_file(tmp_path: Path) -> None:
    assert CONTEXT_ARGV_LIMIT == 8_000
    assert prepare_context(tmp_path, SID, "a" * 8_000) == ContextText("a" * 8_000)
    chosen = prepare_context(tmp_path, SID, "a" * 8_001)
    expected = tmp_path / "sessions" / SID / "context.md"
    assert chosen == ContextFile(expected)
    assert expected.read_text(encoding="utf-8") == "a" * 8_001
    assert stat.S_IMODE(expected.stat().st_mode) == 0o600


def test_the_limit_counts_utf8_bytes_not_characters(tmp_path: Path) -> None:
    fits = "é" * 4_000  # 4 000 characters, 8 000 bytes
    assert prepare_context(tmp_path, SID, fits) == ContextText(fits)
    assert isinstance(prepare_context(tmp_path, SID, fits + "a"), ContextFile)
    assert isinstance(prepare_context(tmp_path, SID, "é" * 3_999 + "€"), ContextFile)


def test_none_gives_none_and_a_short_context_removes_the_stale_file(tmp_path: Path) -> None:
    _ = prepare_context(tmp_path, SID, "a" * 9_000)
    stale = tmp_path / "sessions" / SID / "context.md"
    assert stale.exists()
    assert prepare_context(tmp_path, SID, "short") == ContextText("short")
    assert not stale.exists()
    _ = prepare_context(tmp_path, SID, "a" * 9_000)
    assert prepare_context(tmp_path, SID, None) is None
    assert not stale.exists()


def test_a_short_context_holding_a_nul_goes_to_a_file(tmp_path: Path) -> None:
    chosen = prepare_context(tmp_path, SID, "a\x00b")
    expected = tmp_path / "sessions" / SID / "context.md"
    assert chosen == ContextFile(expected)
    assert expected.read_text(encoding="utf-8") == "a\x00b"


def test_the_file_variant_takes_the_place_before_the_name() -> None:
    argv = claude_argv(
        claude=Path("c"), settings=Path("s"), session_id=SID, permission_mode="auto",
        title="t", context=ContextFile(Path("/s/context.md")),
    )  # fmt: skip
    assert argv[-3:] == ("--append-system-prompt-file", "/s/context.md", "--name=t")
