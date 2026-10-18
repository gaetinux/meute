"""Finding the processes a test left behind, by the `PYTEST_CURRENT_TEST` they inherited.

The run's own `TMUX_TMPDIR` (see conftest) must match too: another pytest run of the same
test, in parallel, has the same `PYTEST_CURRENT_TEST` and its processes are not ours.
"""

import os
from pathlib import Path


def _environ(entry: Path) -> bytes:
    try:
        return (entry / "environ").read_bytes()
    except OSError:  # gone, or not ours
        return b""


def survivors(nodeid: str) -> list[int]:
    """Return the live processes started while the test `nodeid` ran in this run, except us."""
    markers = (
        f"\0PYTEST_CURRENT_TEST={nodeid} (".encode(),
        f"\0TMUX_TMPDIR={os.environ.get('TMUX_TMPDIR', '')}\0".encode(),
    )
    me = os.getpid()
    found: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == me:
            continue
        environ = b"\0" + _environ(entry) + b"\0"
        if all(marker in environ for marker in markers):
            found.append(int(entry.name))
    return sorted(found)


def command_line(pid: int) -> str:
    """Return the command line of `pid`, empty when it is gone."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode(errors="replace").strip()
