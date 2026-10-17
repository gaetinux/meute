"""Errors raised by meute.core."""

from pathlib import Path


class MeuteError(Exception):
    """Base class of every error meute raises on purpose."""


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
