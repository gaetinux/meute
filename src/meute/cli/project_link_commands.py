"""`meute project link` and `unlink`: which project the new sessions of a repository join."""

import os
from pathlib import Path
from typing import Annotated

import typer

from meute.cli.context import CliContext, open_context, require_project
from meute.cli.project_commands import project_app
from meute.cli.repo_scan import scan_repos
from meute.core.db.repos import move_repo, unlink_repo
from meute.core.errors import InvalidInput
from meute.core.paths import resolved
from meute.core.repo import Repo, find_repo
from meute.core.text import printable


def _repo(ctx: CliContext, wanted: str) -> Repo:
    if "/" in wanted:
        wanted = str(resolved(Path(wanted).expanduser()))
    return find_repo(scan_repos(ctx), wanted)


@project_app.command("link")
def link(
    project: Annotated[str, typer.Argument(help="Project name.")],
    repo: Annotated[str, typer.Argument(help="Repository name, or its path if it holds '/'.")],
) -> None:
    """Attach a repository to a project, and detach it from its other projects."""
    with open_context(os.environ) as ctx:
        found = require_project(ctx, project)
        target = _repo(ctx, repo)
        move_repo(ctx.db, found.id, target.id)
        typer.echo(f"Linked: {printable(target.name)} → {printable(found.name)}")


@project_app.command("unlink")
def unlink(
    project: Annotated[str, typer.Argument(help="Project name.")],
    repo: Annotated[str, typer.Argument(help="Repository name, or its path if it holds '/'.")],
) -> None:
    """Detach a repository from a project."""
    with open_context(os.environ) as ctx:
        found = require_project(ctx, project)
        target = _repo(ctx, repo)
        if not unlink_repo(ctx.db, found.id, target.id):
            message = f"{printable(target.name)} is not linked to {printable(found.name)}"
            raise InvalidInput(message)
        typer.echo(f"Unlinked: {printable(target.name)} from {printable(found.name)}")
