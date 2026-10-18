"""`meute repo list`."""

import os
from pathlib import Path
from typing import Annotated

import typer

from meute.cli.context import open_context
from meute.cli.json_out import echo_json
from meute.cli.repo_scan import scan_repos
from meute.core.paths import display_path
from meute.core.repo import repo_to_json

repo_app = typer.Typer(no_args_is_help=True, help="Discovered repositories.")


@repo_app.command("list")
def list_(*, json_: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False) -> None:
    """Scan the configured roots and list the repositories."""
    with open_context(os.environ) as ctx:
        repos = scan_repos(ctx)
        if json_:
            echo_json([repo_to_json(r) for r in repos])
            return
        home = Path.home()
        for repo in repos:
            typer.echo(f"{repo.name}  {repo.kind or '-'}  {display_path(repo.path, home)}")
