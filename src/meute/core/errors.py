"""Errors raised by meute.core."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meute.core.task import Task


class MeuteError(Exception):
    """Base class of every error meute raises on purpose."""

    exit_code = 1


class InvalidInput(MeuteError):  # noqa: N818 — name fixed by the specification
    """The caller supplied a value that meute rejects."""


class ConfigError(MeuteError):
    """The configuration file cannot be parsed or holds an invalid value."""

    def __init__(self, path: Path, message: str) -> None:
        """Build the error for the file `path` and the reason `message`."""
        super().__init__(f"invalid configuration ({path}): {message}")
        self.path = path
        self.message = message


class MigrationError(MeuteError):
    """A database migration failed, or the database is newer than this meute."""


class NotFound(MeuteError):  # noqa: N818 — name fixed by the specification
    """A task, a project or a session does not exist."""

    exit_code = 4

    def __init__(self, entity: str, ident: str) -> None:
        """Build the error for the `entity` kind (task, project, session, ...) and `ident`."""
        super().__init__(f"{entity} not found: {ident}")
        self.entity = entity
        self.ident = ident


class VersionConflict(MeuteError):  # noqa: N818 — name fixed by the specification
    """The task was modified since the version the caller read."""

    exit_code = 3

    def __init__(self, current: "Task") -> None:
        """Build the error carrying the `current` state of the task."""
        super().__init__(f"modified in the meantime (current version: {current.version})")
        self.current = current
