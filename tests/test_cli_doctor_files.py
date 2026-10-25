"""End-to-end tests of `meute doctor`: configuration, database and state folder."""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from conftest import Sandbox
from doctor_support import doctor, level, line, tool_bin
from meute.core.db.schema import SCHEMA_VERSION


def test_an_invalid_configuration_fails_with_its_error(sandbox: Sandbox, tmp_path: Path) -> None:
    config = sandbox.root / "config/meute/config.toml"
    config.parent.mkdir(parents=True)
    _ = config.write_text('[ui]\nrecent_days = "x"\n', encoding="utf-8")
    result = doctor(sandbox, tool_bin(tmp_path))
    assert level(result.stdout, "config") == "fail"
    assert line(result.stdout, "config").startswith(f"invalid configuration ({config}): ")
    assert "recent_days" in line(result.stdout, "config")
    assert result.returncode == 1


def test_a_folder_in_place_of_the_configuration_fails(sandbox: Sandbox, tmp_path: Path) -> None:
    config = sandbox.root / "config/meute/config.toml"
    config.mkdir(parents=True)
    result = doctor(sandbox, tool_bin(tmp_path))
    assert line(result.stdout, "config") == f"{config}: Is a directory"
    assert level(result.stdout, "config") == "fail"


@pytest.mark.skipif(os.geteuid() == 0, reason="root searches any folder")
def test_an_unsearchable_database_folder_fails(sandbox: Sandbox, tmp_path: Path) -> None:
    folder = sandbox.root / "data/meute"
    folder.mkdir(parents=True)
    folder.chmod(0o000)
    try:
        result = doctor(sandbox, tool_bin(tmp_path))
    finally:
        folder.chmod(0o700)
    assert line(result.stdout, "database") == f"{folder / 'meute.db'}: Permission denied"
    assert level(result.stdout, "database") == "fail"


def test_a_valid_configuration_is_ok(sandbox: Sandbox, tmp_path: Path) -> None:
    assert sandbox.run("task", "list").returncode == 0
    result = doctor(sandbox, tool_bin(tmp_path))
    config = sandbox.root / "config/meute/config.toml"
    assert line(result.stdout, "config") == str(config)
    assert level(result.stdout, "config") == "ok"


def _set_schema(sandbox: Sandbox, version: int) -> Path:
    assert sandbox.run("task", "list").returncode == 0  # a migrated database
    path = sandbox.root / "data/meute/meute.db"
    with closing(sqlite3.connect(path)) as conn:
        _ = conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
    return path


def test_the_current_database_is_ok(sandbox: Sandbox, tmp_path: Path) -> None:
    path = _set_schema(sandbox, SCHEMA_VERSION)
    result = doctor(sandbox, tool_bin(tmp_path))
    assert line(result.stdout, "database") == f"{path} (schema {SCHEMA_VERSION})"
    assert level(result.stdout, "database") == "ok"


def test_an_older_database_warns(sandbox: Sandbox, tmp_path: Path) -> None:
    path = _set_schema(sandbox, 3)
    result = doctor(sandbox, tool_bin(tmp_path))
    assert line(result.stdout, "database") == f"{path} (schema 3): migrated at the next start"
    assert level(result.stdout, "database") == "warn"


def test_a_newer_database_fails(sandbox: Sandbox, tmp_path: Path) -> None:
    path = _set_schema(sandbox, 99)
    result = doctor(sandbox, tool_bin(tmp_path))
    expected = f"{path} (schema 99): newer than this meute ({SCHEMA_VERSION})"
    assert line(result.stdout, "database") == expected
    assert level(result.stdout, "database") == "fail"
    assert result.returncode == 1


def test_a_text_file_in_place_of_the_database_fails(sandbox: Sandbox, tmp_path: Path) -> None:
    path = sandbox.root / "data/meute/meute.db"
    path.parent.mkdir(parents=True)
    _ = path.write_text("not a database, just some text that is long enough\n" * 20)
    result = doctor(sandbox, tool_bin(tmp_path))
    assert level(result.stdout, "database") == "fail"
    assert line(result.stdout, "database").startswith(f"{path}: ")
    assert line(result.stdout, "database") != f"{path}: "
    assert result.returncode == 1


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes into any folder")
def test_a_read_only_state_folder_fails(sandbox: Sandbox, tmp_path: Path) -> None:
    state = sandbox.root / "state/meute"
    state.mkdir(parents=True)
    state.chmod(0o500)
    try:
        result = doctor(sandbox, tool_bin(tmp_path))
    finally:
        state.chmod(0o700)
    assert line(result.stdout, "state") == f"{state}: not writable"
    assert level(result.stdout, "state") == "fail"
    assert result.returncode == 1


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes into any folder")
def test_an_absent_state_folder_below_a_read_only_parent_fails(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    parent = sandbox.root / "state"
    parent.mkdir()
    parent.chmod(0o500)
    try:
        result = doctor(sandbox, tool_bin(tmp_path))
    finally:
        parent.chmod(0o700)
    assert line(result.stdout, "state") == f"{parent / 'meute'}: not writable"
    assert level(result.stdout, "state") == "fail"


@pytest.mark.skipif(os.geteuid() == 0, reason="root searches any folder")
def test_a_state_folder_below_an_unsearchable_parent_fails(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    locked = sandbox.root / "locked"
    locked.mkdir()
    locked.chmod(0o000)
    state = locked / "state"
    env = {"PATH": str(tool_bin(tmp_path)), "XDG_STATE_HOME": str(state)}
    try:
        result = sandbox.run("doctor", env=env)
    finally:
        locked.chmod(0o700)
    assert line(result.stdout, "state") == f"{state / 'meute'}: not writable", result.stderr
    assert level(result.stdout, "state") == "fail"


def test_doctor_does_not_create_a_wal_file(sandbox: Sandbox, tmp_path: Path) -> None:
    path = _set_schema(sandbox, SCHEMA_VERSION)
    _ = doctor(sandbox, tool_bin(tmp_path))
    assert not path.with_name("meute.db-wal").exists()
    assert not path.with_name("meute.db-shm").exists()
