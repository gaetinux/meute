"""`meute project link` and `unlink`: which project the new sessions of a repository join."""

import os
from pathlib import Path
from typing import Annotated

import typer

from meute.cli.context import CliContext, open_context, require_project
from meute.cli.project_commands import project_app
from meute.cli.repo_scan import scan_repos
from meute.core.db.repos import list_repos, move_repo, unlink_repo
from meute.core.errors import InvalidInput
from meute.core.paths import resolved
from meute.core.project import Project
from meute.core.repo import Repo, find_repo, repo_matches
from meute.core.text import printable

ProjectArg = Annotated[str, typer.Argument(help="Project name.")]
RepoArg = Annotated[str, typer.Argument(help="Repository name, or its path if it holds '/'.")]


def _targets(ctx: CliContext, project: str, repo: str, *, scan: bool) -> tuple[Project, Repo]:
    """The project and the repository named on the command line.

    The repository is looked up in the database; with `scan`, a miss rescans `repos.roots`.
    """
    found = require_project(ctx, project)
    wanted = resolved(Path(repo).expanduser()) if "/" in repo else repo
    repos = list_repos(ctx.db)
    if scan and not repo_matches(repos, wanted):
        repos = scan_repos(ctx)
    return found, find_repo(repos, wanted)


@project_app.command("link")
def link(project: ProjectArg, repo: RepoArg) -> None:
    """Attach a repository to a project, and detach it from its other projects."""
    with open_context(os.environ) as ctx:
        found, target = _targets(ctx, project, repo, scan=True)
        move_repo(ctx.db, found.id, target.id)
        typer.echo(f"Linked: {printable(target.name)} → {printable(found.name)}")


@project_app.command("unlink")
def unlink(project: ProjectArg, repo: RepoArg) -> None:
    """Detach a repository from a project."""
    with open_context(os.environ) as ctx:  # no scan: a repository never scanned has no link
        found, target = _targets(ctx, project, repo, scan=False)
        if not unlink_repo(ctx.db, found.id, target.id):
            message = f"{printable(target.name)} is not linked to {printable(found.name)}"
            raise InvalidInput(message)
        typer.echo(f"Unlinked: {printable(target.name)} from {printable(found.name)}")
