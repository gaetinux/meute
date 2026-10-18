"""`ingest hook` reads its whole stdin, even past the 1 MiB cap: Claude never gets EPIPE."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

SID = "aaaa1111-0000-4000-8000-000000000000"


@pytest.mark.parametrize("session", [SID, ""])
def test_oversized_payload_is_read_to_its_end(tmp_path: Path, session: str) -> None:
    environ = {key: value for key, value in os.environ.items() if key != "MEUTE_SESSION"}
    environ |= {
        "HOME": str(tmp_path / "home"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "MEUTE_SESSION": session,
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "meute", "ingest", "hook", "Stop"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environ,
    )
    assert process.stdin is not None
    chunk = b"x" * (64 * 1024)
    try:
        for _ in range(32):  # 2 MiB
            _ = process.stdin.write(chunk)
        process.stdin.close()
    finally:
        code = process.wait(timeout=30)
    assert code == 0
