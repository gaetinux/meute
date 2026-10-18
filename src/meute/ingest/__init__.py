"""Hook and statusline ingestion: the latency-critical path, stdlib only."""

import contextlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

_DRAIN_CHUNK = 64 * 1024


def drain(stdin: TextIO) -> None:
    """Read `stdin` to its end, so the writer never blocks on a full pipe."""
    while stdin.read(_DRAIN_CHUNK):
        pass


def _dispatch(args: Sequence[str]) -> None:
    if len(args) == 2 and args[0] == "hook":  # noqa: PLR2004 — `hook <event>`
        from meute.ingest.hook import run_hook  # noqa: PLC0415 — only the hook path pays

        run_hook(args[1], sys.stdin, os.environ)
    elif len(args) == 1 and args[0] == "statusline":
        from meute.ingest.statusline import run_statusline  # noqa: PLC0415 — only this path pays

        run_statusline(sys.stdin, sys.stdout, os.environ)
    else:
        drain(sys.stdin)  # the writer must never block on a pipe nobody reads


def _log(args: Sequence[str], error: BaseException) -> None:
    from meute.core.paths import Paths  # noqa: PLC0415 — only a failure pays
    from meute.ingest.log import log_error  # noqa: PLC0415 — only a failure pays

    state_dir = Paths.from_env(os.environ, home=Path.home()).state_dir
    log_error(state_dir, " ".join(args[:2]), error)


def run(args: Sequence[str]) -> int:
    """Run `ingest <kind> …` and return 0: ingestion must never disturb Claude Code.

    Every failure is logged to `<state>/ingest.log`, except an interruption or exit request.
    """
    try:
        _dispatch(args)
    except (SystemExit, KeyboardInterrupt):
        pass
    except BaseException as error:  # noqa: BLE001 — spec § 7.3: ingest never fails
        with contextlib.suppress(BaseException):  # even the log failing must stay silent
            _log(args, error)
    return 0
