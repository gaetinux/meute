"""`meute layout sync` and the bare `meute` command."""

import os
from collections.abc import Mapping

import typer

from meute.cli.attach import attach
from meute.cli.context import open_context
from meute.cli.tmux_env import TmuxEnv, open_tmux_env
from meute.tmux.layout import Layout, ensure_layout

layout_app = typer.Typer(no_args_is_help=True, help="The meute tmux layout.")


def sync_layout(env: TmuxEnv) -> Layout:
    """Reload the generated configuration into a running server, then build the layout.

    Raises:
        TmuxError: tmux failed.
    """
    if env.tmux.is_running():
        _ = env.tmux.run("source-file", str(env.config_file))
    return ensure_layout(env.tmux, env.spec)


@layout_app.command("sync", hidden=True)
def sync() -> None:
    """Create or repair the layout and apply the narrow mode."""
    with open_context(os.environ) as ctx:
        _ = sync_layout(open_tmux_env(ctx, os.environ))


def open_meute(environ: Mapping[str, str]) -> None:
    """Build the layout, then attach the terminal to it until the user detaches.

    Raises:
        MeuteError: tmux could not attach.
        TmuxError: tmux failed.
    """
    with open_context(environ) as ctx:
        env = open_tmux_env(ctx, environ)
        _ = sync_layout(env)
        keys = ctx.config.keys
        config_file = ctx.paths.config_file
    # The database is closed before attaching, which lasts as long as the user stays.
    if environ.get("TMUX"):
        typer.echo(
            "Warning: meute opens inside your current tmux. If it already uses "
            f"{keys.focus_board} or {keys.focus_main}, change them in the [keys] section "
            f"of {config_file}.",
            err=True,
        )
    attach(env, environ)
