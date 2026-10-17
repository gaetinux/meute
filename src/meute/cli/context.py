"""What every command needs: the clock, the actor, the configuration and the database."""

from collections.abc import Generator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo

from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config, ensure_config, load_config
from meute.core.db.connection import Database
from meute.core.db.projects import list_projects, project_by_name
from meute.core.errors import InvalidInput
from meute.core.instants import parse_zoned
from meute.core.paths import Paths
from meute.core.project import Project

_BUSY_TIMEOUT_MS = 5000
_LOCALTIME = Path("/etc/localtime")


def local_zone(environ: Mapping[str, str]) -> tzinfo:
    """Return the local IANA zone: `TZ` if valid, else `/etc/localtime`, else UTC.

    The zone is never a fixed offset, so `>+1d` and `>tonight` follow daylight saving time.
    """
    name = environ.get("TZ", "")
    if name:
        try:
            return ZoneInfo(name)
        except (ValueError, OSError):  # ZoneInfoNotFoundError is an OSError
            pass
    try:
        with _LOCALTIME.open("rb") as handle:
            return ZoneInfo.from_file(handle)
    except (ValueError, OSError):
        return UTC


def current_time(environ: Mapping[str, str]) -> datetime:
    """Return `MEUTE_NOW` when set (end-to-end tests), else the current local time.

    Raises:
        InvalidInput: `MEUTE_NOW` is not a zoned time.
    """
    frozen = environ.get("MEUTE_NOW")
    if frozen is None:
        return datetime.now(local_zone(environ))
    try:
        return parse_zoned(frozen)
    except InvalidInput:
        message = f"invalid MEUTE_NOW: {frozen}"
        raise InvalidInput(message) from None


@dataclass(frozen=True, slots=True, kw_only=True)
class CliContext:
    """The open database and the settings of one command run."""

    db: Database
    now: datetime
    actor: Actor
    config: Config
    paths: Paths


@contextmanager
def _open_context(environ: Mapping[str, str]) -> Generator[CliContext]:
    now = current_time(environ)
    paths = Paths.from_env(environ, home=Path.home())
    paths.ensure_dirs()
    ensure_config(paths.config_file)
    config = load_config(paths.config_file)
    frozen = "MEUTE_NOW" in environ
    with Database.open(
        paths.db_file,
        busy_timeout_ms=_BUSY_TIMEOUT_MS,
        clock=(lambda: now) if frozen else (lambda: datetime.now(UTC)),
    ) as db:
        actor = Actor(
            author=Author.USER, channel=Channel.CLI, session_id=environ.get("MEUTE_SESSION")
        )
        yield CliContext(db=db, now=now, actor=actor, config=config, paths=paths)


def open_context(environ: Mapping[str, str]) -> AbstractContextManager[CliContext]:
    """Prepare the folders and configuration, open the database and close it on exit."""
    return _open_context(environ)


def require_project(ctx: CliContext, name: str) -> Project:
    """Return the project `name`; a typo never creates a project.

    Raises:
        InvalidInput: the project does not exist.
    """
    project = project_by_name(ctx.db, name)
    if project is not None:
        return project
    names = ", ".join(p.name for p in list_projects(ctx.db))
    listing = f"projects: {names}" if names else "no projects"
    message = f"unknown project: {name} ({listing})"
    raise InvalidInput(message)
