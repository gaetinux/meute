"""A session file already holding the text is left in place, its modes made private."""

import stat
from pathlib import Path

from meute.claude.settings import write_session_file
from meute.core.session import SessionId

SID = SessionId("0b6f1d0e-0000-4000-8000-000000000005")


def test_the_same_text_is_not_written_again(tmp_path: Path) -> None:
    path = write_session_file(tmp_path / "state", SID, "mcp.json", "{}\n")
    inode = path.stat().st_ino
    assert write_session_file(tmp_path / "state", SID, "mcp.json", "{}\n") == path
    assert path.stat().st_ino == inode


def test_a_different_text_replaces_the_file(tmp_path: Path) -> None:
    path = write_session_file(tmp_path / "state", SID, "mcp.json", "{}\n")
    _ = write_session_file(tmp_path / "state", SID, "mcp.json", "[]\n")
    assert path.read_text(encoding="utf-8") == "[]\n"


def test_an_unchanged_file_and_its_folders_are_made_private_again(tmp_path: Path) -> None:
    state = tmp_path / "state"
    path = write_session_file(state, SID, "mcp.json", "{}\n")
    for folder in (state, state / "sessions", path.parent):
        folder.chmod(0o755)
    path.chmod(0o644)
    _ = write_session_file(state, SID, "mcp.json", "{}\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    for folder in (state, state / "sessions", path.parent):
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700


def test_the_comparison_is_exact_byte_for_byte(tmp_path: Path) -> None:
    path = write_session_file(tmp_path / "state", SID, "context.md", "a\r\n")
    _ = write_session_file(tmp_path / "state", SID, "context.md", "a\n")
    assert path.read_bytes() == b"a\n"
