"""The pure core of `meute doctor`: version parsing, checks, rendering and exit code."""

import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st
from syrupy.assertion import SnapshotAssertion

from meute.core.doctor import (
    NOTE_CHECK,
    Check,
    CheckLevel,
    claude_check,
    database_check,
    exit_code,
    git_check,
    options_check,
    parse_version,
    render_checks,
    shown_version,
    timeout_check,
    tmux_check,
)

OK, WARN, FAIL, NOTE = CheckLevel.OK, CheckLevel.WARN, CheckLevel.FAIL, CheckLevel.NOTE
ALL_OPTIONS = (
    "--settings --mcp-config --session-id --resume --permission-mode --append-system-prompt"
)


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("tmux 3.5a", (3, 5)),
        ("tmux next-3.6", (3, 6)),
        ("git version 2.47.3", (2, 47, 3)),
        ("2.1.302 (Claude Code)", (2, 1, 302)),
        ("", None),
        ("tmux master", None),
        ("\x1b[31m", None),
        ("tmux master\n3.4", None),
    ],
)
def test_parse_version(output: str, expected: tuple[int, ...] | None) -> None:
    assert parse_version(output) == expected


@pytest.mark.parametrize(
    ("output", "prefix", "expected"),
    [
        ("tmux 3.5a\n", "tmux ", "3.5a"),
        ("git version 2.47.3", "git version ", "2.47.3"),
        ("2.1.302 (Claude Code)\nmore", "", "2.1.302 (Claude Code)"),
        ("x" * 60, "", "x" * 40),
        ("\x1b]0;pwned\x07 1.2", "", "�]0;pwned� 1.2"),
        ("", "tmux ", ""),
    ],
)
def test_shown_version(output: str, prefix: str, expected: str) -> None:
    assert shown_version(output, prefix) == expected


@given(st.text(), st.text(max_size=5))
def test_parsing_never_raises_and_shows_no_control_character(output: str, prefix: str) -> None:
    parse_version(output)
    shown = shown_version(output, prefix)
    assert len(shown) <= 40
    assert not any(unicodedata.category(c) in {"Cc", "Zl", "Zp"} for c in shown)


@pytest.mark.parametrize(
    ("output", "level"),
    [
        ("tmux 3.1", FAIL),
        ("tmux 3.2", WARN),
        ("tmux 3.3", OK),
        ("tmux 3.10", OK),
        ("tmux next-3.6", OK),
        ("tmux master", FAIL),
    ],
)
def test_tmux_levels(output: str, level: CheckLevel) -> None:
    assert tmux_check(output).level is level


def test_tmux_texts() -> None:
    assert tmux_check("tmux 3.3a\n") == Check(level=OK, name="tmux", text="3.3a")
    assert tmux_check("tmux 3.2").text == "3.2: M-t needs tmux 3.3 or later"
    assert tmux_check("tmux 3.1").text == "3.1: meute needs tmux 3.2 or later"
    assert tmux_check(None) == Check(
        level=FAIL, name="tmux", text="not found: meute needs tmux 3.2 or later"
    )
    assert tmux_check("tmux master").text == "unreadable version: tmux master"


@pytest.mark.parametrize(
    ("output", "level"),
    [("git version 2.35.9", FAIL), ("git version 2.36", OK), ("git version 2.47.3", OK)],
)
def test_git_levels(output: str, level: CheckLevel) -> None:
    assert git_check(output).level is level


def test_git_texts() -> None:
    need = "worktrees and the Git line need git 2.36 or later"
    assert git_check("git version 2.47.3") == Check(level=OK, name="git", text="2.47.3")
    assert git_check("git version 2.35.9").text == f"2.35.9: {need}"
    assert git_check(None) == Check(level=FAIL, name="git", text=f"not found: {need}")
    assert git_check("git version ?") == Check(
        level=FAIL, name="git", text="unreadable version: git version ?"
    )


@pytest.mark.parametrize(
    ("output", "level"),
    [
        ("2.1.300 (Claude Code)", WARN),
        ("2.1.301 (Claude Code)", OK),
        ("2.2.0", OK),
        ("garbage", WARN),
        (None, FAIL),
    ],
)
def test_claude_levels(output: str | None, level: CheckLevel) -> None:
    assert claude_check(output).level is level


def test_claude_texts() -> None:
    assert claude_check("2.1.302 (Claude Code)").text == "2.1.302 (Claude Code)"
    assert claude_check("2.1.300").text == "2.1.300: meute is tested with claude 2.1.301 or later"
    assert claude_check(None).text == "not found: Claude sessions are disabled"
    assert claude_check("garbage").text == "unreadable version: garbage"


def test_options_all_listed() -> None:
    assert options_check(ALL_OPTIONS) == Check(
        level=OK, name="options", text="claude --help lists every option meute uses"
    )


def test_options_match_whole_words() -> None:
    help_text = ALL_OPTIONS.replace("--append-system-prompt", "--append-system-prompt-file")
    check = options_check(help_text)
    assert check.level is FAIL
    assert check.text == "claude --help does not list: --append-system-prompt"


def test_options_missing_are_listed_in_constraint_order() -> None:
    help_text = "--mcp-config --session-id --permission-mode --append-system-prompt"
    assert options_check(help_text).text == "claude --help does not list: --settings, --resume"


def test_timeout_check() -> None:
    assert timeout_check("claude") == Check(
        level=FAIL, name="claude", text="claude did not answer within 5 s"
    )


def test_a_line_can_be_named_apart_from_its_tool() -> None:
    assert timeout_check("claude", name="options") == Check(
        level=FAIL, name="options", text="claude did not answer within 5 s"
    )
    assert tmux_check(None, name="server") == Check(
        level=FAIL, name="server", text="not found: meute needs tmux 3.2 or later"
    )


def test_database_checks() -> None:
    assert database_check("/d/m.db", 5, 5) == Check(
        level=OK, name="database", text="/d/m.db (schema 5)"
    )
    older = database_check("/d/m.db", 3, 5)
    assert (older.level, older.text) == (WARN, "/d/m.db (schema 3): migrated at the next start")
    newer = database_check("/d/m.db", 9, 5)
    assert (newer.level, newer.text) == (FAIL, "/d/m.db (schema 9): newer than this meute (5)")
    absent = database_check("/d/m.db", None, 5)
    assert (absent.level, absent.text) == (WARN, "/d/m.db: created at the first start")


def test_note_check() -> None:
    assert NOTE_CHECK.level is NOTE
    assert NOTE_CHECK.name == "note"
    assert NOTE_CHECK.text == (
        "--append-system-prompt-file (used above 8000 bytes of context) is not in claude --help "
        "and cannot be checked"
    )


def _mixed() -> list[Check]:
    return [
        Check(level=OK, name="tmux", text="3.5a"),
        Check(
            level=WARN, name="claude", text="2.1.300: meute is tested with claude 2.1.301 or later"
        ),
        Check(
            level=FAIL,
            name="git",
            text="not found: worktrees and the Git line need git 2.36 or later",
        ),
        Check(level=OK, name="config", text="/home/u/.config/meute/config.toml"),
        NOTE_CHECK,
    ]


def test_render_mixed_levels(snapshot: SnapshotAssertion) -> None:
    assert render_checks(_mixed()) == snapshot


def test_render_without_problem_has_no_closing_line() -> None:
    out = render_checks([Check(level=OK, name="tmux", text="3.5a"), NOTE_CHECK])
    assert out.splitlines()[0] == "ok    tmux      3.5a"
    assert "problem" not in out


def test_render_one_problem_is_singular() -> None:
    out = render_checks([Check(level=WARN, name="database", text="x"), NOTE_CHECK])
    assert out.splitlines()[-1] == "1 problem found"


def test_render_has_no_trailing_space() -> None:
    out = render_checks([Check(level=FAIL, name="tmux", text="")])
    assert out == "fail  tmux\n1 problem found"
    assert all(line == line.rstrip() for line in out.splitlines())


def test_exit_code() -> None:
    assert exit_code(_mixed()) == 1
    assert exit_code([Check(level=WARN, name="a", text=""), NOTE_CHECK]) == 0
    assert exit_code([]) == 0


def test_parse_version_survives_huge_digit_runs() -> None:
    assert parse_version("1." + "9" * 5000) is not None
    assert parse_version("9" * 5000 + ".1") is not None
    assert parse_version("٣.٤") is None
