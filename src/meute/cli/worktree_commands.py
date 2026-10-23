"""The `meute worktree` commands: list the linked worktrees, remove one with its branch kept."""

import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from meute.cli.context import open_context
from meute.cli.json_out import echo_json
from meute.cli.session_launch import resolve_folder
from meute.cli.session_refresh import refresh
from meute.cli.tmux_env import open_tmux_env
from meute.cli.worktree_removal import (
    find_git_or_fail,
    inspect_worktree,
    live_session_folders,
    remove_checked,
)
from meute.core.db.repos import list_repos
from meute.core.db.samples import latest_metrics_by_session
from meute.core.db.sessions import list_sessions
from meute.core.errors import InvalidInput
from meute.core.paths import display_path
from meute.core.text import printable
from meute.core.worktrees import Worktree, WorktreeCheck, listed_text, parse_worktree_list
from meute.git.discover import main_repo_of
from meute.git.run import GitError
from meute.git.worktree import CHECK_TIMEOUT, list_worktrees_text, worktree_changes

worktree_app = typer.Typer(no_args_is_help=True, help="Linked Git worktrees.")

_SHORT_HEAD = 7


def _main_repo(folder: Path) -> Path:
    repo = main_repo_of(resolve_folder(folder))
    if repo is None:
        message = f"not in a git repository: {display_path(folder, Path.home())}"
        raise InvalidInput(message)
    return repo


def _branch_text(worktree: Worktree) -> str:
    if worktree.branch is None:
        return f"(detached {worktree.head[:_SHORT_HEAD]})"
    return worktree.branch


@worktree_app.command("list")
def list_(
    repo: Annotated[
        Path | None, typer.Argument(help="A repository (default: every known one).")
    ] = None,
    *,
    json_: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """List the linked worktrees: path, branch, `*` when changed, `locked` and `missing`."""
    if repo is None:
        with open_context(os.environ) as ctx:
            repos = [known.path for known in list_repos(ctx.db) if known.path.is_dir()]
    else:
        repos = [_main_repo(repo)]
    git = find_git_or_fail(os.environ)
    home = Path.home()
    found: list[tuple[Path, Worktree, bool]] = []
    failed = False
    for main in repos:
        try:
            found.extend(_linked(git, main))
        except GitError as failure:  # told on its own line: the other repositories still show
            failed = True
            typer.echo(printable(f"meute: {display_path(main, home)}: {failure}"), err=True)
    if json_:
        echo_json(
            {
                "worktrees": [
                    {
                        "repo": str(main),
                        "path": str(worktree.path),
                        "branch": worktree.branch,
                        "dirty": dirty,
                        "locked": worktree.locked,
                        "missing": not worktree.path.is_dir(),
                    }
                    for main, worktree, dirty in found
                ]
            }
        )
    else:
        for _, worktree, dirty in found:
            typer.echo(
                f"{printable(display_path(worktree.path, home))}"
                f"  {printable(_branch_text(worktree))}"
                + (" *" if dirty else "")
                + ("  locked" if worktree.locked else "")
                + ("" if worktree.path.is_dir() else "  missing")
            )
    if failed:
        raise typer.Exit(code=1)


def _linked(git: Path, main: Path) -> list[tuple[Path, Worktree, bool]]:
    """The linked worktrees of `main`, each with whether it has changes.

    A worktree whose folder is absent (a locked one on removable media) is never read.

    Raises:
        GitError: git failed or timed out.
    """
    text = list_worktrees_text(git, main, timeout=CHECK_TIMEOUT, environ=os.environ)
    return [
        (
            main,
            worktree,
            worktree.path.is_dir()
            and bool(worktree_changes(git, worktree.path, environ=os.environ)),
        )
        for worktree in sorted(parse_worktree_list(text, main), key=lambda w: w.path)
    ]


def _confirmed(question: str) -> bool:
    typer.echo(f"{question} y/n ", err=True, nl=False)
    return sys.stdin.readline().strip().lower() in {"y", "yes"}


def _question(check: WorktreeCheck, shown: str) -> str:
    if not check.clean:
        return "remove anyway?"
    kept = "" if check.branch is None else f" (branch {printable(check.branch)} is kept)"
    return f"remove worktree {shown}?{kept}"


@worktree_app.command("remove")
def remove(
    path: Annotated[Path, typer.Argument(help="The worktree folder.")],
    *,
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Remove it despite changes or unpushed commits.")
    ] = False,
) -> None:
    """Remove a linked worktree, its branch kept; never the main folder or a live one."""
    with open_context(os.environ) as ctx:
        _ = refresh(ctx, open_tmux_env(ctx, os.environ), assume=False)
        sessions = list_sessions(ctx.db)
        metrics = latest_metrics_by_session(ctx.db, [session.id for session in sessions])
    check = inspect_worktree(os.environ, path, live_session_folders(sessions, metrics))
    shown = printable(display_path(check.path, Path.home()))
    for line in (*listed_text(check.changes), *listed_text(check.commits)):
        typer.echo(line)
    if not yes and (force or check.clean) and not _confirmed(_question(check, shown)):
        typer.echo("Cancelled.")
        return
    remove_checked(os.environ, check, force=force)
    typer.echo(f"worktree removed: {shown}")
