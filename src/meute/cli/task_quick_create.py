"""Creating a task from a quick entry, for the board and its quick-entry popup."""

from collections.abc import Sequence

from meute.cli.context import CliContext, local_now
from meute.core.actor import Actor, Author, Channel
from meute.core.db.connection import Database
from meute.core.db.projects import project_refs
from meute.core.db.repos import create_repo_project, list_repos
from meute.core.db.task_update import update_task
from meute.core.db.tasks import create_task, get_task
from meute.core.errors import VersionConflict
from meute.core.project import ProjectId, ProjectRef
from meute.core.quick_add import parse_quick_add
from meute.core.quick_preview import (
    NewFromRepo,
    ProjectChoice,
    choice_project_id,
    resolve_quick_project,
)
from meute.core.task import NewTask, Task, TaskId, TaskPatch

TUI_ACTOR = Actor(author=Author.USER, channel=Channel.TUI)


def repo_names(db: Database) -> tuple[str, ...]:
    """Return the names of the known repositories, which `@name` may also name."""
    return tuple(repo.name for repo in list_repos(db))


def chosen_project_id(db: Database, choice: ProjectChoice) -> ProjectId | None:
    """Return the id of the project `choice` names, creating it from its repository if new.

    Raises:
        InvalidInput: the project is unknown (nothing is written).
        sqlite3.Error: the database failed (locked, read-only…) while creating the project.
    """
    found = choice_project_id(choice)
    if isinstance(found, NewFromRepo):
        return create_repo_project(db, found.name).id
    return found


def create_quick_task(
    ctx: CliContext,
    text: str,
    default: ProjectRef | None,
    projects: Sequence[ProjectRef] | None = None,
) -> Task:
    """Create the task a quick entry (`Title @project ! >due`) describes, as the TUI user.

    Without `@`, the task goes to `default`; `@none` makes it floating. `@name` is resolved
    against `projects`, read from the database when not given, then the known repositories:
    a repository's name creates its project, attached to it, before the task.

    Raises:
        InvalidInput: the title is empty, or the project is unknown (nothing is written).
        NotFound: the project was deleted between its resolution and the task's creation.
        sqlite3.Error: the database failed (locked, read-only…); a project made from a
            repository may then remain, and is reused by the next attempt.
    """
    parsed = parse_quick_add(text, local_now(ctx))  # an empty title stops here
    # The rule the live preview shows.
    refs = project_refs(ctx.db) if projects is None else projects
    choice = resolve_quick_project(parsed.project, default, refs, repo_names(ctx.db))
    new = NewTask(
        title=parsed.title,
        priority=parsed.priority,
        due=parsed.due,
        project_id=chosen_project_id(ctx.db, choice),
    )
    return create_task(ctx.db, new, TUI_ACTOR)


def move_to_repo_project(db: Database, task_id: TaskId, version: int, name: str) -> Task:
    """Move a task still at `version` to the project created from the repository `name`.

    Raises:
        VersionConflict: the task changed since `version` (no project is created).
        NotFound: no such task.
        sqlite3.Error: the database failed.
    """
    current = get_task(db, task_id)
    if current.version != version:
        raise VersionConflict(current)
    project = create_repo_project(db, name)
    return update_task(db, task_id, version, TaskPatch(project_id=project.id), TUI_ACTOR)
