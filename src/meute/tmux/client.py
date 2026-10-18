"""Client of the `tmux` binary on a dedicated socket."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from meute.tmux.errors import CommandFailed, NotInstalled, TooOld
from meute.tmux.parse import MIN_VERSION, TmuxVersion, parse_version


def is_no_server(error: CommandFailed) -> bool:
    """Whether the command failed only because no tmux server is running."""
    return "no server running" in error.stderr or "error connecting to" in error.stderr


@dataclass(frozen=True, slots=True, kw_only=True)
class Tmux:
    """Runs tmux commands against the server on `socket` (`tmux -L`)."""

    socket: str
    config_file: Path | None = None

    def base_args(self) -> list[str]:
        """The command prefix selecting the socket (and the configuration file)."""
        args = ["tmux", "-L", self.socket]
        if self.config_file is not None:
            args += ["-f", str(self.config_file)]
        return args

    def run(self, *args: str) -> str:
        """Run one tmux command and return its stdout without the final newline.

        Raises:
            NotInstalled: the tmux binary is missing.
            CommandFailed: tmux exited with a non-zero status.
        """
        try:
            done = subprocess.run(  # noqa: S603 — fixed argv, no shell; "tmux" is resolved through PATH by design
                [*self.base_args(), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except FileNotFoundError as error:
            raise NotInstalled from error
        if done.returncode != 0:
            raise CommandFailed(args, done.stderr.rstrip())
        return done.stdout.removesuffix("\n")

    def is_running(self) -> bool:
        """Whether a server answers on the socket."""
        try:
            self.run("list-sessions")
        except CommandFailed as error:
            if is_no_server(error):
                return False
            raise
        return True

    def has_session(self, name: str) -> bool:
        """Whether a session called exactly `name` exists."""
        try:
            self.run("has-session", "-t", f"={name}")
        except CommandFailed:
            return False
        return True

    def kill_server(self) -> None:
        """Stop the server and every session in it."""
        self.run("kill-server")


def _classify_version(output: str) -> TmuxVersion | None:
    version = parse_version(output)
    if version is not None and version < MIN_VERSION:
        found = output.strip().removeprefix("tmux").strip()
        raise TooOld(found)
    return version


def check_version() -> TmuxVersion | None:
    """Check the installed tmux; None means the version is unreadable and accepted.

    Raises:
        NotInstalled: the tmux binary is missing.
        TooOld: the installed tmux is older than 3.2.
    """
    try:
        done = subprocess.run(
            ["tmux", "-V"],  # noqa: S607 — tmux is resolved through PATH by design
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as error:
        raise NotInstalled from error
    return _classify_version(done.stdout)
