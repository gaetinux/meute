"""`meute project add` and `list`."""

import os
from typing import Annotated

import typer

from meute.cli.context import open_context
from meute.cli.json_out import echo_json
from meute.core.db.projects import create_project, list_projects
from meute.core.project import project_to_json

project_app = typer.Typer(no_args_is_help=True, help="Manage projects.")


@project_app.command("add")
def add(
    name: Annotated[str, typer.Argument(help="Project name.")],
    description: Annotated[str, typer.Option(help="What the project is about.")] = "",
) -> None:
    """Create a project."""
    with open_context(os.environ) as ctx:
        project = create_project(ctx.db, name, description)
        typer.echo(f"Project created: {project.name}")


@project_app.command("list")
def list_(*, json_: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False) -> None:
    """List projects by name."""
    with open_context(os.environ) as ctx:
        projects = list_projects(ctx.db)
        if json_:
            echo_json([project_to_json(p) for p in projects])
        else:
            for project in projects:
                typer.echo(project.name)
