"""The switch to WAL happens under the migration lock, so concurrent first opens never collide."""

import fcntl
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

_OPEN = """
import sys
from pathlib import Path
from meute.core.db.connection import Database
with Database.open(Path(sys.argv[1]), busy_timeout_ms=30000):
    pass
"""


def _is_wal(path: Path) -> bool:
    header = path.read_bytes()[:20]
    return header[18:20] == b"\x02\x02"  # file format read/write versions: 2 means WAL


def test_wal_switch_waits_for_the_migration_lock(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        conn.execute("CREATE TABLE t (x)")  # a rollback-journal file, as plan 1 left them
    assert not _is_wal(path)
    lock_fd = os.open(tmp_path / "meute.db.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        worker = subprocess.Popen([sys.executable, "-c", _OPEN, str(path)], stderr=subprocess.PIPE)
        time.sleep(1.5)  # long enough for the worker to start and reach the lock
        assert worker.poll() is None
        assert not _is_wal(path)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    _, err = worker.communicate(timeout=60)
    assert (worker.returncode, err) == (0, b"")
    assert _is_wal(path)
