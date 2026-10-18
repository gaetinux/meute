"""Scanning the configured roots and storing what is found."""

from pathlib import Path

from meute.cli.context import CliContext
from meute.core.db.repos import sync_repos
from meute.core.repo import NewRepo, Repo
from meute.git.discover import discover, expand_home


def scan_repos(ctx: CliContext) -> list[Repo]:
    """Discover repositories under `repos.roots`, store them and return all known ones."""
    home = Path.home()
    roots = [expand_home(root, home) for root in ctx.config.repos.roots]
    found = [
        NewRepo(path=repo.path, name=repo.name, kind=None if repo.kind is None else repo.kind.value)
        for repo in discover(roots)
    ]
    return sync_repos(ctx.db, found)
