"""The `meute` MCP server: the task tools over an `McpBackend`."""

import json
from collections.abc import Callable
from dataclasses import field

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

from meute.core.errors import MeuteError
from meute.core.json_types import JsonValue
from meute.core.task import KEEP, Keep
from meute.mcp.backend import McpBackend, TaskChanges

SERVER_NAME = "meute"
INTERNAL_ERROR = "internal error"


class _Omitted(str):
    """The value of a `task_update` field the caller left out, told apart by identity."""

    __slots__ = ()


_OMITTED = _Omitted()


def _omitted() -> _Omitted:
    return _OMITTED


# A default factory keeps the field optional without a `default` in the published schema,
# so an omitted field (KEEP) stays distinct from an explicit null (clear).
_OPTIONAL = field(default_factory=_omitted)


def _kept(value: str | None) -> str | Keep | None:
    return KEEP if value is _OMITTED else value


def _text(text: str, *, is_error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=is_error)


def _answer(
    run: Callable[[], JsonValue], on_unexpected: Callable[[BaseException], None]
) -> CallToolResult:
    # The tool builds its own result: the SDK would prefix every error message with the tool name.
    try:
        return _text(json.dumps(run()))
    except MeuteError as error:
        return _text(str(error), is_error=True)
    except Exception as error:  # noqa: BLE001 — journaled, then answered without details
        on_unexpected(error)
        return _text(INTERNAL_ERROR, is_error=True)


def build_server(
    backend: McpBackend, *, on_unexpected: Callable[[BaseException], None]
) -> MCPServer:
    server = MCPServer(SERVER_NAME, log_level="WARNING")

    def tool[F: Callable[..., CallToolResult]](fn: F) -> F:
        server.add_tool(fn, structured_output=False)
        return fn

    @tool
    def task_list(
        *,
        project: str | None = None,
        status: str | None = None,
        due: str | None = None,
        include_done: bool = False,
    ) -> CallToolResult:
        """List tasks, by project name, status and due (overdue, today or week)."""
        return _answer(lambda: backend.task_list(project, status, due, include_done), on_unexpected)

    @tool
    def task_read(*, id: int) -> CallToolResult:  # noqa: A002 — the tool input is named `id`
        """Read a task with its notes."""
        return _answer(lambda: backend.task_read(id), on_unexpected)

    @tool
    def task_create(
        *,
        title: str,
        description: str | None = None,
        priority: str | None = None,
        due: str | None = None,
        project: str | None = None,
    ) -> CallToolResult:
        """Create a task; due is an ISO date or an ISO instant with a time zone."""
        return _answer(
            lambda: backend.task_create(title, description, priority, due, project), on_unexpected
        )

    @tool
    def task_update(  # noqa: PLR0913 — one parameter per tool input
        *,
        id: int,  # noqa: A002 — the tool input is named `id`
        expected_version: int,
        title: str | None = _OPTIONAL,
        description: str | None = _OPTIONAL,
        priority: str | None = _OPTIONAL,
        due: str | None = _OPTIONAL,
        project: str | None = _OPTIONAL,
    ) -> CallToolResult:
        """Update the fields of a task, but not its status; null clears a field."""
        changes = TaskChanges(
            title=_kept(title),
            description=_kept(description),
            priority=_kept(priority),
            due=_kept(due),
            project=_kept(project),
        )
        return _answer(lambda: backend.task_update(id, expected_version, changes), on_unexpected)

    @tool
    def task_set_status(
        *,
        id: int,  # noqa: A002 — the tool input is named `id`
        status: str,
        expected_version: int,
        reason: str | None = None,
    ) -> CallToolResult:
        """Set the status of a task (todo, in_progress, blocked, review, done); blocked needs a reason."""  # noqa: E501 — one-line tool description
        return _answer(
            lambda: backend.task_set_status(id, status, reason, expected_version), on_unexpected
        )

    @tool
    def task_note_add(*, id: int, body: str) -> CallToolResult:  # noqa: A002 — the tool input is named `id`
        """Add a note to a task."""
        return _answer(lambda: backend.task_note_add(id, body), on_unexpected)

    @tool
    def task_link_session(*, id: int) -> CallToolResult:  # noqa: A002 — the tool input is named `id`
        """Link the calling Claude session to a task."""
        return _answer(lambda: backend.task_link_session(id), on_unexpected)

    return server


def run_stdio(server: MCPServer) -> None:
    server.run("stdio")
