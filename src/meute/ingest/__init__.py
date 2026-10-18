"""Hook and statusline ingestion: the latency-critical path, stdlib only."""

import contextlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path


def _dispatch(args: Sequence[str]) -> None:
    if len(args) == 2 and args[0] == "hook":  # noqa: PLR2004 — `hook <event>`
        from meute.ingest.hook import run_hook  # noqa: PLC0415 — only the hook path pays

        run_hook(args[1], sys.stdin, os.environ)


def _log(args: Sequence[str], error: BaseException) -> None:
    from meute.core.instants import utc_now  # noqa: PLC0415 — only a failure pays
    from meute.core.paths import Paths  # noqa: PLC0415 — only a failure pays
    from meute.ingest.log import log_failure  # noqa: PLC0415 — only a failure pays

    state_dir = Paths.from_env(os.environ, home=Path.home()).state_dir
    log_failure(state_dir, " ".join(args[:2]), error, utc_now())


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
