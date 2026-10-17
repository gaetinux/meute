"""Tests for project creation and lookup."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.projects import create_project, list_projects, project_by_name
from meute.core.errors import InvalidInput


def test_project_names_are_unique_ignoring_case(db: Database) -> None:
    create_project(db, "Meute")
    assert project_by_name(db, "meute") is not None
    with pytest.raises(InvalidInput, match=r"^project already exists: MEUTE$"):
        create_project(db, "MEUTE")
    with pytest.raises(InvalidInput, match="cannot be empty"):
        create_project(db, "  ")


def test_project_names_fold_non_ascii_case(db: Database) -> None:
    create_project(db, "Équipe")
    with pytest.raises(InvalidInput):
        create_project(db, "équipe")
    found = project_by_name(db, " ÉQUIPE ")
    assert found is not None
    assert found.name == "Équipe"


def test_list_projects_is_sorted_by_name(db: Database) -> None:
    for name in ("zeta", "Alpha", "beta"):
        create_project(db, name)
    assert [p.name for p in list_projects(db)] == ["Alpha", "beta", "zeta"]
    assert project_by_name(db, "x") is None


def test_create_project_only_maps_unique_violations(file_db: tuple[Database, Path]) -> None:
    db, path = file_db
    with closing(sqlite3.connect(path)) as raw:
        raw.execute("ALTER TABLE projects RENAME TO projects_gone")
    with pytest.raises(sqlite3.OperationalError):
        create_project(db, "x")


def test_create_project_reraises_non_unique_integrity_errors(
    file_db: tuple[Database, Path],
) -> None:
    db, path = file_db
    with closing(sqlite3.connect(path, autocommit=True)) as raw:
        raw.execute(
            "CREATE TRIGGER refuse BEFORE INSERT ON projects"
            " BEGIN SELECT RAISE(ABORT, 'refused'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        create_project(db, "x")
