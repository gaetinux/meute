"""Projects in the database."""

import sqlite3

from meute.core.db.connection import Database
from meute.core.db.rows import (
    PROJECT_SELECT,
    fetch_all,
    fetch_one,
    row_to_project,
)
from meute.core.errors import InvalidInput, NotFound
from meute.core.instants import to_db
from meute.core.project import Project, ProjectId, ProjectRef, name_key
from meute.core.text import INSTRUCTIONS_CONTROL, has_control_character


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
            row = fetch_one(
                conn,
                "INSERT INTO projects (name, name_key, description, created_at)"
                " VALUES (?, ?, ?, ?)"
                " RETURNING id, name, description, instructions, created_at",
                (clean, name_key(clean), description, to_db(db.now())),
            )
    except sqlite3.IntegrityError as error:
        if error.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
            message = f"project already exists: {clean}"
            raise InvalidInput(message) from error
        raise
    if row is None:
        message = "INSERT returned no row"
        raise RuntimeError(message)
    return row_to_project(row)


def project_by_name(db: Database, name: str) -> Project | None:
    """Return the project called `name` (ignoring case and outer spaces), or None."""
    row = fetch_one(
        db.conn,
        f"{PROJECT_SELECT} WHERE name_key = ?",
        (name_key(name),),
    )
    return None if row is None else row_to_project(row)


def list_projects(db: Database) -> list[Project]:
    """Return every project, sorted by name key then id."""
    rows = fetch_all(
        db.conn,
        f"{PROJECT_SELECT} ORDER BY name_key, id",
    )
    return [row_to_project(row) for row in rows]


def project_refs(db: Database) -> tuple[ProjectRef, ...]:
    """Return a reference (id and name) to every project, sorted as `list_projects`."""
    return tuple(ProjectRef(id=project.id, name=project.name) for project in list_projects(db))


def set_project_instructions(db: Database, project_id: ProjectId, instructions: str) -> Project:
    """Replace the instructions of a project; an empty string clears them.

    Raises:
        InvalidInput: they hold a control character other than a newline or a tab.
        NotFound: no such project.
    """
    if has_control_character(instructions):
        raise InvalidInput(INSTRUCTIONS_CONTROL)
    with db.transaction() as conn:
        row = fetch_one(
            conn,
            "UPDATE projects SET instructions = ? WHERE id = ?"
            " RETURNING id, name, description, instructions, created_at",
            (instructions, project_id),
        )
    if row is None:
        entity = "project"
        raise NotFound(entity, str(project_id))
    return row_to_project(row)
