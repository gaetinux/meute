"""Finding the processes a test left behind, by the `PYTEST_CURRENT_TEST` they inherited."""

import os
from pathlib import Path


def _environ(entry: Path) -> bytes:
    try:
        return (entry / "environ").read_bytes()
    except OSError:  # gone, or not ours
        return b""


def survivors(nodeid: str) -> list[int]:
    """Return the live processes started while the test `nodeid` ran, except this one."""
    marker = f"\0PYTEST_CURRENT_TEST={nodeid} (".encode()
    me = os.getpid()
    return sorted(
        int(entry.name)
        for entry in Path("/proc").iterdir()
        if entry.name.isdigit() and int(entry.name) != me and marker in b"\0" + _environ(entry)
    )
