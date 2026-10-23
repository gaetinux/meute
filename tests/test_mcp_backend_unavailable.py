"""Database failures during an MCP tool call become `meute database unavailable: ...`."""

import sqlite3
from datetime import UTC
from pathlib import Path

import pytest

import meute.cli.context as cli_context
from meute.cli import mcp_backend
from meute.cli.mcp_backend import CliMcpBackend
from meute.core.errors import MeuteError
from meute.core.paths import Paths
from support import FIXED


def backend(paths: Paths) -> CliMcpBackend:
    return CliMcpBackend(paths, None, lambda: FIXED, UTC)


def paths_in(tmp_path: Path) -> Paths:
    return Paths.from_roots(
        config_home=tmp_path / "c", data_home=tmp_path / "d", state_home=tmp_path / "s"
    )


def test_a_locked_database_is_unavailable_then_available_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = paths_in(tmp_path)
    b = backend(paths)
    b.task_create("T", None, None, None, None)
    monkeypatch.setattr(cli_context, "BUSY_TIMEOUT_MS", 50)
    locker = sqlite3.connect(paths.db_file, autocommit=True)
    locker.execute("BEGIN EXCLUSIVE")
    try:
        assert b.task_read(1)["title"] == "T"  # in WAL mode, readers are not blocked
        for call in (
            lambda: b.task_note_add(1, "x"),
            lambda: b.task_create("U", None, None, None, None),
        ):
            with pytest.raises(MeuteError, match=r"^meute database unavailable: .*locked"):
                call()
    finally:
        locker.execute("ROLLBACK")
        locker.close()
    assert b.task_note_add(1, "x") == {"note_id": 1}
    assert b.task_create("U", None, None, None, None) == {"id": 2, "version": 1}


def test_a_database_that_cannot_be_created_is_unavailable(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    paths = Paths.from_roots(config_home=tmp_path, data_home=blocker, state_home=tmp_path)
    with pytest.raises(MeuteError, match=r"^meute database unavailable: "):
        backend(paths).task_read(1)


@pytest.mark.parametrize(
    "error", [sqlite3.OperationalError("disk I/O error"), OSError("no space left")]
)
def test_an_environment_failure_in_the_middle_of_a_call_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fail(*_: object) -> None:
        raise error

    b = backend(paths_in(tmp_path))
    b.task_create("T", None, None, None, None)
    monkeypatch.setattr(mcp_backend, "get_task", fail)
    with pytest.raises(MeuteError, match=r"^meute database unavailable: "):
        b.task_read(1)


@pytest.mark.parametrize(
    "error", [sqlite3.IntegrityError("constraint"), sqlite3.ProgrammingError("bug")]
)
def test_a_bug_in_the_middle_of_a_call_stays_unexpected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def fail(*_: object) -> None:
        raise error

    b = backend(paths_in(tmp_path))
    b.task_create("T", None, None, None, None)
    monkeypatch.setattr(mcp_backend, "get_task", fail)
    with pytest.raises(type(error)):
        b.task_read(1)
