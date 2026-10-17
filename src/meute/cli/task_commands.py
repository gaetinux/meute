"""`meute task add`, `list` and `show`."""

import os
from typing import Annotated

import typer

from meute.cli.context import open_context, require_project
from meute.cli.json_out import echo_json
from meute.cli.render import preview_line, task_detail, task_line
from meute.cli.task_app import task_app
from meute.core.db.task_notes import notes
from meute.core.db.tasks import (
    AnyProject,
    Floating,
    InProject,
    ProjectFilter,
    TaskFilter,
    create_task,
    get_task,
    list_tasks,
)
from meute.core.quick_add import parse_quick_add
from meute.core.status import parse_status_kind
from meute.core.task import NewTask, TaskId, note_to_json, task_to_json
from meute.core.views import sort_for_display


@task_app.command("add")
def add(
    words: Annotated[list[str], typer.Argument(help="Title, with @project, ! / !! and >due.")],
    *,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show how the input is read; create nothing.")
    ] = False,
) -> None:
    """Create a task from a quick entry such as: Review the PR @meute ! >tomorrow."""
    with open_context(os.environ) as ctx:
        parsed = parse_quick_add(" ".join(words), ctx.now)
        project = None if parsed.project is None else require_project(ctx, parsed.project)
        if dry_run:
            typer.echo(f"Parsed: {preview_line(parsed, ctx.now)}")
            return
        task = create_task(
            ctx.db,
            NewTask(
                title=parsed.title,
                priority=parsed.priority,
                due=parsed.due,
                project_id=None if project is None else project.id,
            ),
            ctx.actor,
        )
        typer.echo(f"Created: {task_line(task, ctx.now)}")


@task_app.command("list")
def list_(
    *,
    all_: Annotated[bool, typer.Option("--all", help="Include finished tasks.")] = False,
    project: Annotated[str | None, typer.Option(help="Only tasks of this project.")] = None,
    floating: Annotated[bool, typer.Option(help="Only tasks without a project.")] = False,
    status: Annotated[
        str | None, typer.Option(help="Only this status: todo, in_progress, blocked, review, done.")
    ] = None,
    json_: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """List tasks, most urgent first."""
    if project is not None and floating:
        message = "--project and --floating cannot be used together"
        raise typer.BadParameter(message)
    kind = None if status is None else parse_status_kind(status)
    with open_context(os.environ) as ctx:
        scope: ProjectFilter = AnyProject()
        if project is not None:
            scope = InProject(project_id=require_project(ctx, project).id)
        elif floating:
            scope = Floating()
        tasks = sort_for_display(
            list_tasks(ctx.db, TaskFilter(include_done=all_, project=scope, status=kind)), ctx.now
        )
        if json_:
            echo_json([task_to_json(task) for task in tasks])
        else:
            for task in tasks:
                typer.echo(task_line(task, ctx.now))


@task_app.command("show")
def show(
    task_id: Annotated[int, typer.Argument(metavar="ID", help="Task number.")],
    *,
    json_: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Show every field of a task and its notes."""
    with open_context(os.environ) as ctx:
        task = get_task(ctx.db, TaskId(task_id))
        task_notes = notes(ctx.db, task.id)
        if json_:
            echo_json({**task_to_json(task), "notes": [note_to_json(n) for n in task_notes]})
        else:
            typer.echo(task_detail(task, task_notes, ctx.now))
