"""`meute task quick`: the `M-t` window, run by tmux in a popup above any pane."""

import os
from typing import TYPE_CHECKING

import typer

from meute.cli.context import ENVIRONMENT_ERRORS, CliContext, local_now, open_context
from meute.cli.task_app import task_app
from meute.cli.task_quick_create import create_quick_task
from meute.cli.tmux_env import open_tmux_env
from meute.core.db.projects import project_refs
from meute.core.db.repos import list_repos
from meute.core.db.sessions import get_session
from meute.core.errors import MeuteError, NotFound
from meute.core.project import ProjectRef
from meute.core.session import SessionId
from meute.core.session_project import session_project
from meute.core.task import Task
from meute.tmux.client import Tmux
from meute.tmux.errors import TmuxError
from meute.tmux.layout import displayed_meute_id

if TYPE_CHECKING:  # type names only: Textual stays out of the start-up
    from meute.tui.quick_task import QuickContext


def displayed_project(ctx: CliContext, tmux: Tmux) -> ProjectRef | None:
    """Return the project of the session shown in the main area of meute, if any.

    Without a meute server, a layout or a displayed session, the task floats.
    """
    try:
        shown = displayed_meute_id(tmux)
    except TmuxError:  # no meute server: nothing is displayed
        return None
    if shown is None:
        return None
    try:
        session = get_session(ctx.db, SessionId(shown))
    except NotFound:  # a pane of a session deleted meanwhile
        return None
    repos = {repo.id: repo for repo in list_repos(ctx.db)}
    return session_project(session, projects=project_refs(ctx.db), repos=repos)


class CliQuickBackend:
    """The window's backend: the database of `ctx`, tasks going to `default` without `@`."""

    def __init__(self, ctx: CliContext, default: ProjectRef | None) -> None:
        self._ctx = ctx
        self._default = default

    def context(self) -> "QuickContext":
        """Return the clock, the default project and all the projects."""
        from meute.tui.quick_task import QuickContext  # noqa: PLC0415 — keeps Textual out of every other command's start-up

        return QuickContext(
            now=local_now(self._ctx), default=self._default, projects=project_refs(self._ctx.db)
        )

    def create(self, text: str) -> Task:
        """Create the task `text` describes, as the TUI user.

        Raises:
            MeuteError: nothing was created (bad entry, or the database failed).
        """
        try:
            return create_quick_task(self._ctx, text, self._default)
        except ENVIRONMENT_ERRORS as error:  # a locked database keeps the window open
            raise MeuteError(str(error)) from error


@task_app.command("quick", hidden=True)
def quick() -> None:
    """Open the quick task window (bound to M-t in meute's tmux)."""
    from meute.tui.quick_task import QuickTaskApp  # noqa: PLC0415 — keeps Textual out of every other command's start-up

    with open_context(os.environ) as ctx:
        tmux = open_tmux_env(ctx, os.environ).tmux
        app = QuickTaskApp(CliQuickBackend(ctx, displayed_project(ctx, tmux)))
        app.run()
    raise typer.Exit(app.return_code or 0)
