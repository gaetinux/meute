"""Projects in the database."""

import sqlite3

from meute.core.db.connection import Database
from meute.core.db.rows import fetch_all, fetch_one, row_to_project
from meute.core.errors import InvalidInput
from meute.core.instants import to_db
from meute.core.project import Project


def create_project(db: Database, name: str, description: str = "") -> Project:
    """Create a project; names are unique ignoring case (Unicode case folding).

    Raises:
        InvalidInput: the name is empty or already used.
    """
    clean = name.strip()
    if not clean:
        message = "project name cannot be empty"
        raise InvalidInput(message)
    try:
        with db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO projects (name, name_key, description, created_at)"
                " VALUES (?, ?, ?, ?)",
                (clean, clean.casefold(), description, to_db(db.now())),
            )
            row = fetch_one(
                conn,
                "SELECT id, name, description, instructions, created_at FROM projects WHERE id = ?",
                (cursor.lastrowid,),
            )
    except sqlite3.IntegrityError as error:
        if error.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
            message = f"project already exists: {clean}"
            raise InvalidInput(message) from error
        raise
    if row is None:
        message = "inserted project not found"
        raise RuntimeError(message)
    return row_to_project(row)


def project_by_name(db: Database, name: str) -> Project | None:
    """Return the project called `name` (ignoring case and outer spaces), or None."""
    row = fetch_one(
        db.conn,
        "SELECT id, name, description, instructions, created_at FROM projects WHERE name_key = ?",
        (name.strip().casefold(),),
    )
    return None if row is None else row_to_project(row)


def list_projects(db: Database) -> list[Project]:
    """Return every project, sorted by name key then id."""
    rows = fetch_all(
        db.conn,
        "SELECT id, name, description, instructions, created_at"
        " FROM projects ORDER BY name_key, id",
    )
    return [row_to_project(row) for row in rows]
