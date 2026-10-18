"""Locations of meute's files, following the XDG base directory specification."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True, kw_only=True)
class Paths:
    """Where meute reads its configuration and keeps its data."""

    config_file: Path
    db_file: Path
    state_dir: Path

    @staticmethod
    def from_roots(*, config_home: Path, data_home: Path, state_home: Path) -> "Paths":
        """Build the paths below the three XDG base directories."""
        return Paths(
            config_file=config_home / "meute" / "config.toml",
            db_file=data_home / "meute" / "meute.db",
            state_dir=state_home / "meute",
        )

    @staticmethod
    def from_env(environ: Mapping[str, str], *, home: Path) -> "Paths":
        """Build the paths from the XDG variables, ignoring empty or relative values."""

        def root(variable: str, default: str) -> Path:
            value = environ.get(variable, "")
            return Path(value) if value and Path(value).is_absolute() else home / default

        return Paths.from_roots(
            config_home=root("XDG_CONFIG_HOME", ".config"),
            data_home=root("XDG_DATA_HOME", ".local/share"),
            state_home=root("XDG_STATE_HOME", ".local/state"),
        )

    def ensure_dirs(self) -> None:
        """Create the folders holding the configuration, the database and the state."""
        for folder in (self.config_file.parent, self.db_file.parent, self.state_dir):
            folder.mkdir(parents=True, exist_ok=True)


def display_path(path: Path, home: Path | None) -> str:
    """Return `path` as `~` or `~/…` when it is `home` or below it, else unchanged."""
    if home is None or not path.is_relative_to(home):
        return str(path)
    relative = path.relative_to(home)
    return "~" if relative == Path() else f"~/{relative}"
