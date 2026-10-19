"""Opening the database must not disturb a connection that is already open in this process.

POSIX drops every lock a process holds on a file when it closes any descriptor of that file:
the board opens a second connection in a worker thread (to stop a session) while its own is open.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

from meute.core.db.connection import Database

_WRITER = (
    "import sqlite3, sys\n"
    "for _ in range(300):\n"
    "    conn = sqlite3.connect(sys.argv[1], timeout=10)\n"
    "    conn.execute('INSERT INTO z VALUES (2)')\n"
    "    conn.commit()\n"
    "    conn.close()\n"
)


def test_opening_beside_an_open_connection_keeps_it_healthy(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    errors: list[str] = []
    with Database.open(path, busy_timeout_ms=10_000) as main:
        main.conn.execute("CREATE TABLE z (x)")

        def reopen() -> None:
            for _ in range(200):
                try:
                    with Database.open(path, busy_timeout_ms=10_000) as other:
                        other.conn.execute("INSERT INTO z VALUES (1)")
                except Exception as error:  # noqa: BLE001 — collected, then asserted empty
                    errors.append(f"other: {error}")

        thread = threading.Thread(target=reopen)
        writer = subprocess.Popen(
            [sys.executable, "-c", _WRITER, str(path)], stderr=subprocess.PIPE, text=True
        )
        thread.start()
        while thread.is_alive() or writer.poll() is None:
            try:
                main.conn.execute("INSERT INTO z VALUES (3)")
            except Exception as error:  # noqa: BLE001 — collected, then asserted empty
                errors.append(f"main: {error}")
                break
            # Leave the write lock to the others: SQLite's busy handler is no queue.
            time.sleep(0.001)
        thread.join()
        _, stderr = writer.communicate()
        if writer.returncode != 0:
            errors.append(f"writer: {stderr.strip().splitlines()[-1:]}")
    assert errors == []
