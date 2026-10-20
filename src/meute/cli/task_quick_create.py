"""Creating a task from a quick entry, for the board and its quick-entry popup."""

from collections.abc import Sequence

from meute.cli.context import CliContext, local_now
from meute.core.actor import Actor, Author, Channel
from meute.core.db.projects import project_refs
from meute.core.db.tasks import create_task
from meute.core.project import ProjectRef
from meute.core.quick_add import parse_quick_add
from meute.core.quick_preview import choice_project_id, resolve_quick_project
from meute.core.task import NewTask, Task

TUI_ACTOR = Actor(author=Author.USER, channel=Channel.TUI)


def create_quick_task(
    ctx: CliContext,
    text: str,
    default: ProjectRef | None,
    projects: Sequence[ProjectRef] | None = None,
) -> Task:
    """Create the task a quick entry (`Title @project ! >due`) describes, as the TUI user.

    Without `@`, the task goes to `default`; `@none` makes it floating. `@name` is resolved
    against `projects`, read from the database when not given.

    Raises:
        InvalidInput: the title is empty, or the project is unknown (nothing is written).
    """
    parsed = parse_quick_add(text, local_now(ctx))
    # The rule the live preview shows.
    refs = project_refs(ctx.db) if projects is None else projects
    choice = resolve_quick_project(parsed.project, default, refs)
    project_id = choice_project_id(choice)
    new = NewTask(
        title=parsed.title, priority=parsed.priority, due=parsed.due, project_id=project_id
    )
    return create_task(ctx.db, new, TUI_ACTOR)
