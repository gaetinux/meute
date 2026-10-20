"""Creating a task from a quick entry, for the board and its quick-entry popup."""

from typing import assert_never

from meute.cli.context import CliContext
from meute.core.actor import Actor, Author, Channel
from meute.core.db.projects import list_projects
from meute.core.db.tasks import create_task
from meute.core.errors import InvalidInput
from meute.core.project import ProjectId, ProjectRef
from meute.core.quick_add import parse_quick_add
from meute.core.quick_preview import (
    Displayed,
    Floating,
    Named,
    UnknownProject,
    resolve_quick_project,
)
from meute.core.task import NewTask, Task

TUI_ACTOR = Actor(author=Author.USER, channel=Channel.TUI)


def _project_id(ctx: CliContext, name: str | None, default: ProjectRef | None) -> ProjectId | None:
    """Resolve the `@name` of an entry with the rule the live preview shows."""
    refs = [ProjectRef(id=p.id, name=p.name) for p in list_projects(ctx.db)]
    choice = resolve_quick_project(name, default, refs)
    match choice:
        case Named(project=ref) | Displayed(project=ref):
            return ref.id
        case Floating():
            return None
        case UnknownProject(name=unknown):
            message = f"unknown project: {unknown}"
            raise InvalidInput(message)
        case _:
            assert_never(choice)


def create_quick_task(ctx: CliContext, text: str, default: ProjectRef | None) -> Task:
    """Create the task a quick entry (`Title @project ! >due`) describes, as the TUI user.

    Without `@`, the task goes to `default`; `@none` makes it floating.

    Raises:
        InvalidInput: the title is empty, or the project is unknown (nothing is written).
    """
    parsed = parse_quick_add(text, ctx.db.now())
    project_id = _project_id(ctx, parsed.project, default)
    new = NewTask(
        title=parsed.title, priority=parsed.priority, due=parsed.due, project_id=project_id
    )
    return create_task(ctx.db, new, TUI_ACTOR)
