"""The MCP task tools over meute's database: one connection per tool call."""

import sqlite3
from collections.abc import Callable, Generator, Mapping
from contextlib import ExitStack, contextmanager
from datetime import datetime, tzinfo

from meute.cli.context import open_database, open_existing_database
from meute.core.actor import Actor, Author, Channel
from meute.core.db.connection import Database
from meute.core.db.projects import project_by_name, project_refs
from meute.core.db.repos import list_repos
from meute.core.db.sessions import get_session, link_session_task
from meute.core.db.task_notes import add_note, notes
from meute.core.db.task_update import update_task
from meute.core.db.tasks import (
    AnyProject,
    InProject,
    ProjectFilter,
    TaskFilter,
    create_task,
    get_task,
    list_tasks,
)
from meute.core.errors import InvalidInput, MeuteError, NotFound
from meute.core.json_types import JsonObject, JsonValue
from meute.core.mcp_data import (
    due_matches,
    parse_due,
    parse_due_filter,
    parse_priority,
    parse_status,
    task_json,
    task_summary_json,
)
from meute.core.paths import Paths
from meute.core.project import ProjectId
from meute.core.session import SessionId
from meute.core.session_project import session_project
from meute.core.status import Priority, parse_status_kind
from meute.core.task import KEEP, Keep, NewTask, TaskId, TaskPatch
from meute.core.views import sort_for_display
from meute.ingest.hook import session_from_env
from meute.mcp.backend import TaskChanges


def caller_session(environ: Mapping[str, str]) -> SessionId | None:
    """Return `MEUTE_SESSION` when it is a session id in its exact (canonical) form, else None."""
    parsed = session_from_env(environ)
    # session_from_env also lower-cases: only the exact form names the caller.
    return parsed if parsed == environ.get("MEUTE_SESSION") else None


_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def _in_range(name: str, value: int, low: int, high: int) -> int:
    """`value` when it lies within `low`..`high` (SQLite's integer range at most)."""
    if not low <= value <= high:
        message = f"{name} out of range: {value}"
        raise InvalidInput(message)
    return value


def _task_id(value: int) -> TaskId:
    return TaskId(_in_range("id", value, 1, _INT64_MAX))  # ids start at 1


def _version(value: int) -> int:
    return _in_range("expected_version", value, _INT64_MIN, _INT64_MAX)


def _unavailable(error: BaseException) -> MeuteError:
    return MeuteError(f"meute database unavailable: {error}")


class CliMcpBackend:
    """Runs each task tool as Claude, through the MCP channel, in the calling session."""

    def __init__(
        self,
        paths: Paths,
        caller: SessionId | None,
        clock: Callable[[], datetime],
        zone: tzinfo,
    ) -> None:
        """Keep what a tool call needs; nothing is opened before the first call."""
        self._paths = paths
        self._zone = zone
        self._caller = caller
        self._clock = clock
        self._actor = Actor(author=Author.CLAUDE, channel=Channel.MCP, session_id=caller)
        self._migrated = False

    @contextmanager
    def _database(self) -> Generator[Database]:
        """Open the database for one call; a missing or locked one is `unavailable`.

        The first successful call creates and migrates it; later calls open it as it is.
        """
        opener = open_existing_database if self._migrated else open_database
        with ExitStack() as stack:
            try:
                db = stack.enter_context(opener(self._paths, self._clock))
            except (sqlite3.Error, OSError) as error:
                raise _unavailable(error) from None
            self._migrated = True
            try:
                yield db
            except (sqlite3.OperationalError, OSError) as error:
                raise _unavailable(error) from None

    def _project_id(self, db: Database, name: str) -> ProjectId:
        project = project_by_name(db, name)
        if project is None:
            message = f"unknown project: {name}"
            raise InvalidInput(message)
        return project.id

    def _caller_project(self, db: Database) -> ProjectId | None:
        if self._caller is None:
            return None
        try:
            session = get_session(db, self._caller)
        except NotFound:
            return None
        if session.project_id is not None:
            return session.project_id
        repos = {repo.id: repo for repo in list_repos(db)}
        found = session_project(session, projects=project_refs(db), repos=repos)
        return None if found is None else found.id

    def _now(self, db: Database) -> datetime:
        return db.now().astimezone(self._zone)

    def task_list(
        self,
        project: str | None,
        status: str | None,
        due: str | None,
        include_done: bool,  # noqa: FBT001 — signature fixed by McpBackend
    ) -> JsonValue:
        """List the tasks matching the filters, most urgent first."""
        kind = None if status is None else parse_status_kind(status)
        due_filter = None if due is None else parse_due_filter(due)
        with self._database() as db:
            scope: ProjectFilter = AnyProject()
            if project is not None:
                scope = InProject(project_id=self._project_id(db, project))
            now = self._now(db)
            found = list_tasks(
                db, TaskFilter(include_done=include_done, project=scope, status=kind)
            )
            kept = (
                found
                if due_filter is None
                else [t for t in found if due_matches(t.due, due_filter, now)]
            )
            return [task_summary_json(task) for task in sort_for_display(kept, now)]

    def task_read(self, task_id: int) -> JsonObject:
        """Return a task with its notes."""
        checked = _task_id(task_id)
        with self._database() as db:
            task = get_task(db, checked)
            return task_json(task, notes(db, task.id))

    def task_create(
        self,
        title: str,
        description: str | None,
        priority: str | None,
        due: str | None,
        project: str | None,
    ) -> JsonObject:
        """Create a task, in the project of the calling session when none is given."""
        parsed_priority = None if priority is None else parse_priority(priority)
        parsed_due = None if due is None else parse_due(due)
        with self._database() as db:
            project_id = (
                self._caller_project(db) if project is None else self._project_id(db, project)
            )
            task = create_task(
                db,
                NewTask(
                    title=title,
                    description=description or "",
                    priority=Priority.NORMAL if parsed_priority is None else parsed_priority,
                    due=parsed_due,
                    project_id=project_id,
                ),
                self._actor,
            )
            return {"id": task.id, "version": task.version}

    def task_update(self, task_id: int, expected_version: int, changes: TaskChanges) -> JsonObject:
        """Change the fields of a task, but not its status."""
        checked, version = _task_id(task_id), _version(expected_version)
        patch_title = _required("title", changes.title)
        patch_priority = _required("priority", changes.priority)
        parsed_priority = (
            patch_priority if isinstance(patch_priority, Keep) else parse_priority(patch_priority)
        )
        parsed_due = _kept_or(changes.due, parse_due)
        with self._database() as db:
            project_id = _kept_or(changes.project, lambda name: self._project_id(db, name))
            description = "" if changes.description is None else changes.description
            patch = TaskPatch(
                title=patch_title,
                description=description,
                priority=parsed_priority,
                due=parsed_due,
                project_id=project_id,
            )
            task = update_task(db, checked, version, patch, self._actor)
            return {"version": task.version}

    def task_set_status(
        self, task_id: int, status: str, reason: str | None, expected_version: int
    ) -> JsonObject:
        """Set the status of a task."""
        checked, version = _task_id(task_id), _version(expected_version)
        new_status = parse_status(status, reason)
        with self._database() as db:
            task = update_task(db, checked, version, TaskPatch(status=new_status), self._actor)
            return {"version": task.version}

    def task_note_add(self, task_id: int, body: str) -> JsonObject:
        """Add a note to a task."""
        checked = _task_id(task_id)
        with self._database() as db:
            return {"note_id": add_note(db, checked, body, self._actor).id}

    def task_link_session(self, task_id: int) -> JsonObject:
        """Link the calling session to a task."""
        checked = _task_id(task_id)
        if self._caller is None:
            message = "no calling session: MEUTE_SESSION is not set to a session id"
            raise InvalidInput(message)
        with self._database() as db:
            session = link_session_task(db, self._caller, checked)
            return {"session_id": session.id, "task_id": task_id}


def _required(field: str, value: str | Keep | None) -> str | Keep:
    if value is None:
        message = f"{field} cannot be cleared"
        raise InvalidInput(message)
    return value


def _kept_or[T](value: str | Keep | None, read: Callable[[str], T]) -> T | Keep | None:
    if value is None:
        return None
    return KEEP if isinstance(value, Keep) else read(value)
