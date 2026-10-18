"""The ingest failure log: one bounded line per failure, rotation, never raising."""

import os
from pathlib import Path

import pytest

from meute.ingest.log import log_failure
from support import FIXED


def test_one_line_per_failure_with_instant_command_and_type(tmp_path: Path) -> None:
    log_failure(tmp_path, "hook Stop", ValueError("bad\nthing"), FIXED)
    assert (tmp_path / "ingest.log").read_text(encoding="utf-8") == (
        "2026-10-14T08:30:00.000000Z hook Stop ValueError: bad thing\n"
    )


def test_message_is_cut_to_two_hundred_characters(tmp_path: Path) -> None:
    log_failure(tmp_path, "hook Stop", ValueError("x" * 900), FIXED)
    line = (tmp_path / "ingest.log").read_text(encoding="utf-8").splitlines()[0]
    assert line.endswith("ValueError: " + "x" * 200)


def test_log_rotates_past_one_mebibyte(tmp_path: Path) -> None:
    log = tmp_path / "ingest.log"
    log.write_text("old\n" * 300_000, encoding="utf-8")
    log_failure(tmp_path, "hook Stop", ValueError("new"), FIXED)
    assert (tmp_path / "ingest.log.1").read_text(encoding="utf-8").startswith("old\n")
    assert log.read_text(encoding="utf-8").count("\n") == 1


def test_log_never_raises_when_the_folder_is_not_writable(tmp_path: Path) -> None:
    if os.geteuid() == 0:
        pytest.skip("root ignores directory permissions")
    folder = tmp_path / "locked"
    folder.mkdir()
    folder.chmod(0o500)
    try:
        log_failure(folder, "hook Stop", ValueError("x"), FIXED)
    finally:
        folder.chmod(0o700)
    assert not (folder / "ingest.log").exists()


def test_log_never_raises_when_the_folder_is_missing(tmp_path: Path) -> None:
    log_failure(tmp_path / "absent" / "deeper", "hook Stop", ValueError("x"), FIXED)


def test_lone_surrogate_in_the_message_is_still_logged(tmp_path: Path) -> None:
    log_failure(tmp_path, "hook Stop", ValueError("a\ud800b"), FIXED)
    assert "ValueError: a" in (tmp_path / "ingest.log").read_text(encoding="utf-8")
