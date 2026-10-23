"""`meute mcp`: serve the task tools over stdio, with nothing but the protocol on stdout."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from meute.cli.context import current_time
from meute.cli.mcp_backend import CliMcpBackend, caller_session
from meute.core.clock import local_zone
from meute.core.paths import Paths
from meute.ingest.log import log_error
from meute.mcp.server import build_server, run_stdio

MCP_LOG = "mcp.log"


def journal(state_dir: Path) -> Callable[[BaseException], None]:
    """Return the function that writes an unexpected exception to `<state_dir>/mcp.log`.

    It never raises: the SDK would answer the caller with the raw exception otherwise.
    """

    def write(error: BaseException) -> None:
        try:
            log_error(state_dir, "mcp", error, name=MCP_LOG)
        except Exception:  # noqa: BLE001 — the journal must never disturb the server
            return

    return write


def serve(environ: Mapping[str, str]) -> None:
    """Run the MCP server on stdio until the client closes it.

    The database is neither opened nor migrated here: the first tool call does it.
    """
    now = current_time(environ)
    clock = (lambda: now) if "MEUTE_NOW" in environ else (lambda: datetime.now(UTC))
    paths = Paths.from_env(environ, home=Path.home())
    backend = CliMcpBackend(paths, caller_session(environ), clock, local_zone(environ))
    run_stdio(build_server(backend, on_unexpected=journal(paths.state_dir)))
