"""Creating a task from a quick entry, for the board and its quick-entry popup."""

from meute.cli.context import CliContext
from meute.core.actor import Actor, Author, Channel
from meute.core.db.projects import project_by_name
from meute.core.db.tasks import create_task
from meute.core.errors import InvalidInput
from meute.core.project import ProjectId, ProjectRef
from meute.core.quick_add import parse_quick_add
from meute.core.task import NewTask, Task

TUI_ACTOR = Actor(author=Author.USER, channel=Channel.TUI)
_FLOATING = "none"


def _project_id(ctx: CliContext, name: str | None, default: ProjectRef | None) -> ProjectId | None:
    """Resolve the `@name` of an entry: `@none` floats, an unknown name is refused."""
    if name is None:
        return None if default is None else default.id
    if name.casefold() == _FLOATING:
        return None
    project = project_by_name(ctx.db, name)
    if project is None:
        message = f"unknown project: {name}"
        raise InvalidInput(message)
    return project.id


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
