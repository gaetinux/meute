"""The `meute mcp` journal: mcp.log rotates like ingest.log and never raises."""

from pathlib import Path

from meute.cli.mcp_command import journal
from meute.ingest.log import log_failure
from support import FIXED


class Unprintable(Exception):  # noqa: N818 — a test double
    def __str__(self) -> str:
        message = "no text"
        raise RuntimeError(message)


def test_the_log_name_is_a_parameter_and_ingest_log_is_left_alone(tmp_path: Path) -> None:
    log_failure(tmp_path, "mcp", ValueError("boom"), FIXED, name="mcp.log")
    assert (tmp_path / "mcp.log").read_text(encoding="utf-8") == (
        "2026-10-14T08:30:00.000000Z mcp ValueError: boom\n"
    )
    assert not (tmp_path / "ingest.log").exists()


def test_mcp_log_rotates_past_one_mebibyte(tmp_path: Path) -> None:
    (tmp_path / "mcp.log").write_text("old\n" * 300_000, encoding="utf-8")
    log_failure(tmp_path, "mcp", ValueError("new"), FIXED, name="mcp.log")
    assert (tmp_path / "mcp.log.1").read_text(encoding="utf-8").startswith("old\n")
    assert (tmp_path / "mcp.log").read_text(encoding="utf-8").count("\n") == 1


def test_the_journal_writes_the_exception_to_mcp_log(tmp_path: Path) -> None:
    journal(tmp_path)(ValueError("boom"))
    assert "mcp ValueError: boom" in (tmp_path / "mcp.log").read_text(encoding="utf-8")


def test_the_journal_never_raises_when_the_message_cannot_be_built(tmp_path: Path) -> None:
    journal(tmp_path)(Unprintable())


def test_the_journal_never_raises_when_the_folder_is_missing(tmp_path: Path) -> None:
    journal(tmp_path / "absent" / "deeper")(ValueError("x"))
