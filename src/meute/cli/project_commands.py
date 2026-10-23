"""`meute project add`, `list`, `edit` and `show`."""

import os
from pathlib import Path
from typing import Annotated

import typer

from meute.cli.context import open_context
from meute.cli.json_out import echo_json
from meute.core.db.projects import (
    create_project,
    list_projects,
    project_by_name,
    set_project_instructions,
)
from meute.core.db.repos import project_repos
from meute.core.errors import InvalidInput, NotFound
from meute.core.project import Project, project_to_json
from meute.core.repo import repo_to_json
from meute.core.text import INSTRUCTIONS_CONTROL, has_control_character, printable

project_app = typer.Typer(no_args_is_help=True, help="Manage projects.")


@project_app.command("add")
def add(
    name: Annotated[str, typer.Argument(help="Project name.")],
    description: Annotated[str, typer.Option(help="What the project is about.")] = "",
) -> None:
    """Create a project."""
    with open_context(os.environ) as ctx:
        project = create_project(ctx.db, name, description)
        typer.echo(f"Project created: {printable(project.name)}")


@project_app.command("list")
def list_(*, json_: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False) -> None:
    """List projects by name."""
    with open_context(os.environ) as ctx:
        projects = list_projects(ctx.db)
        if json_:
            echo_json([project_to_json(p) for p in projects])
        else:
            for project in projects:
                typer.echo(printable(project.name))


def _read_instructions(instructions: str | None, instructions_file: Path | None) -> str:
    text = _given_instructions(instructions, instructions_file)
    if has_control_character(text):
        raise InvalidInput(INSTRUCTIONS_CONTROL)
    return text


def _given_instructions(instructions: str | None, instructions_file: Path | None) -> str:
    if instructions is not None and instructions_file is not None:
        message = "give either --instructions or --instructions-file, not both"
        raise InvalidInput(message)
    if instructions is not None:
        return instructions
    if instructions_file is None:
        message = "give --instructions or --instructions-file"
        raise InvalidInput(message)
    shown = printable(str(instructions_file))
    try:
        return instructions_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        message = f"cannot read {shown}: not valid UTF-8"
        raise InvalidInput(message) from None
    except OSError as error:
        message = f"cannot read {shown}: {printable(str(error))}"
        raise InvalidInput(message) from error


def _require_project(project: Project | None, name: str) -> Project:
    if project is None:
        entity = "project"
        raise NotFound(entity, name)
    return project


@project_app.command("edit")
def edit(
    name: Annotated[str, typer.Argument(help="Project name.")],
    instructions: Annotated[
        str | None, typer.Option(help="Instructions for its Claude sessions; empty clears them.")
    ] = None,
    instructions_file: Annotated[
        Path | None, typer.Option(help="A UTF-8 file holding the instructions.")
    ] = None,
) -> None:
    """Set the instructions of a project."""
    text = _read_instructions(instructions, instructions_file)
    with open_context(os.environ) as ctx:
        project = _require_project(project_by_name(ctx.db, name), name)
        set_project_instructions(ctx.db, project.id, text)


@project_app.command("show")
def show(
    name: Annotated[str, typer.Argument(help="Project name.")],
    *,
    json_: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """Show a project: description, instructions and repositories."""
    with open_context(os.environ) as ctx:
        project = _require_project(project_by_name(ctx.db, name), name)
        repos = project_repos(ctx.db, project.id)
        if json_:
            echo_json(
                {
                    "name": project.name,
                    "description": project.description,
                    "instructions": project.instructions,
                    "repos": [repo_to_json(repo) for repo in repos],
                }
            )
            return
        typer.echo(f"name: {printable(project.name)}")
        typer.echo(f"description: {printable(project.description)}")
        typer.echo(f"instructions: {printable(project.instructions, keep_newlines=True)}")
        typer.echo("repos:")
        for repo in repos:
            typer.echo(f"  {printable(repo.name)} {printable(str(repo.path))}")
