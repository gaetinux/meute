"""Attaching the terminal to the `meute:main` window."""

import subprocess
from collections.abc import Mapping

from meute.cli.tmux_env import TmuxEnv
from meute.core.errors import MeuteError
from meute.tmux.names import MAIN_TARGET


def attach_command(env: TmuxEnv, environ: Mapping[str, str]) -> tuple[list[str], dict[str, str]]:
    """Return the attach arguments and their environment, without `TMUX`.

    Without `TMUX`, tmux agrees to attach even when meute runs inside another tmux.
    """
    args = [*env.tmux.base_args(), "attach-session", "-t", MAIN_TARGET]
    return args, {key: value for key, value in environ.items() if key != "TMUX"}


def attach(env: TmuxEnv, environ: Mapping[str, str]) -> None:
    """Attach the terminal to `meute:main` until the user detaches.

    Raises:
        MeuteError: tmux could not attach.
    """
    args, child_environ = attach_command(env, environ)
    done = subprocess.run(args, env=child_environ, check=False)  # noqa: S603 — fixed argv, no shell
    if done.returncode != 0:
        message = "attaching to tmux failed"
        raise MeuteError(message)
