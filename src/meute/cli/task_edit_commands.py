"""`meute task edit`, `status`, `note` and `rm`."""

import os
import sys
from typing import Annotated

import typer

from meute.cli.context import CliContext, open_context, require_project
from meute.cli.render import task_line
from meute.cli.task_app import task_app
from meute.core.db.task_notes import add_note
from meute.core.db.task_update import delete_task, update_task
from meute.core.db.tasks import get_task
from meute.core.due_parse import parse_due
from meute.core.errors import InvalidInput
from meute.core.project import ProjectId
from meute.core.status import parse_priority, parse_status_kind, status_from_kind
from meute.core.task import KEEP, Due, TaskId, TaskPatch

_TaskNumber = Annotated[int, typer.Argument(metavar="ID", help="Task number.")]
_ExpectedVersion = Annotated[
    int | None,
    typer.Option(help="Fail if the task changed since this version (default: the current one)."),
]
_CLEAR = "none"


def stdin_is_terminal() -> bool:
    """Whether a person can answer a prompt."""
    return sys.stdin.isatty()


def _version(ctx: CliContext, task_id: TaskId, expected: int | None) -> int:
    return get_task(ctx.db, task_id).version if expected is None else expected


def _due(token: str, ctx: CliContext) -> Due | None:
    if token == _CLEAR:
        return None
    due = parse_due(token, ctx.now)
    if due is None:
        message = f"invalid due date: {token}"
        raise InvalidInput(message)
    return due


def _project_id(name: str, ctx: CliContext) -> ProjectId | None:
    return None if name == _CLEAR else require_project(ctx, name).id


@task_app.command("edit")
def edit(  # noqa: PLR0913 — each Typer option is a parameter
    task_id: _TaskNumber,
    *,
    title: Annotated[str | None, typer.Option(help="New title.")] = None,
    description: Annotated[str | None, typer.Option(help="New description.")] = None,
    priority: Annotated[str | None, typer.Option(help="normal, high or urgent.")] = None,
    due: Annotated[str | None, typer.Option(help="A due date such as tomorrow, or none.")] = None,
    project: Annotated[str | None, typer.Option(help="A project name, or none.")] = None,
    expected_version: _ExpectedVersion = None,
) -> None:
    """Change a task's title, description, priority, due date or project."""
    with open_context(os.environ) as ctx:
        patch = TaskPatch(
            title=KEEP if title is None else title,
            description=KEEP if description is None else description,
            priority=KEEP if priority is None else parse_priority(priority),
            due=KEEP if due is None else _due(due, ctx),
            project_id=KEEP if project is None else _project_id(project, ctx),
        )
        _update(ctx, TaskId(task_id), expected_version, patch)


def _update(ctx: CliContext, task_id: TaskId, expected: int | None, patch: TaskPatch) -> None:
    task = update_task(ctx.db, task_id, _version(ctx, task_id, expected), patch, ctx.actor)
    typer.echo(task_line(task, ctx.now))


@task_app.command("status")
def status(
    task_id: _TaskNumber,
    kind: Annotated[str, typer.Argument(help="todo, in_progress, blocked, review or done.")],
    *,
    reason: Annotated[str | None, typer.Option(help="Why the task is blocked.")] = None,
    expected_version: _ExpectedVersion = None,
) -> None:
    """Change a task's status."""
    new_status = status_from_kind(parse_status_kind(kind), reason)
    with open_context(os.environ) as ctx:
        _update(ctx, TaskId(task_id), expected_version, TaskPatch(status=new_status))


@task_app.command("note")
def note(
    task_id: _TaskNumber,
    words: Annotated[list[str], typer.Argument(metavar="TEXT...", help="The note.")],
) -> None:
    """Add a note to a task."""
    with open_context(os.environ) as ctx:
        added = add_note(ctx.db, TaskId(task_id), " ".join(words), ctx.actor)
        typer.echo(f"Note added to #{added.task_id}")


@task_app.command("rm")
def rm(
    task_id: _TaskNumber,
    *,
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
    expected_version: _ExpectedVersion = None,
) -> None:
    """Delete a task; its history is kept."""
    with open_context(os.environ) as ctx:
        task = get_task(ctx.db, TaskId(task_id))
        if not yes:
            _confirm(f"Delete #{task.id} “{task.title}”? [y/N] ")
        delete_task(
            ctx.db,
            task.id,
            task.version if expected_version is None else expected_version,
            ctx.actor,
        )
        typer.echo(f"Deleted: #{task.id}")


def _confirm(prompt: str) -> None:
    if not stdin_is_terminal():
        message = "confirmation required: rerun with --yes"
        raise InvalidInput(message)
    typer.echo(prompt, nl=False)
    if sys.stdin.readline().strip().lower() not in {"y", "yes"}:
        message = "deletion cancelled"
        raise InvalidInput(message)
