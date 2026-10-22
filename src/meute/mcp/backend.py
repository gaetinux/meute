"""What the MCP task tools need from meute: one synchronous method per tool."""

from dataclasses import dataclass
from typing import Protocol

from meute.core.json_types import JsonObject, JsonValue
from meute.core.task import Keep


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskChanges:
    """The fields `task_update` changes: `KEEP` leaves one as is, `None` clears it."""

    title: str | Keep | None
    description: str | Keep | None
    priority: str | Keep | None
    due: str | Keep | None
    project: str | Keep | None


class McpBackend(Protocol):
    """Runs each task tool against the database; raises `MeuteError` for a refusal."""

    def task_list(
        self,
        project: str | None,
        status: str | None,
        due: str | None,
        include_done: bool,  # noqa: FBT001 — one plain parameter per tool input
    ) -> JsonValue: ...

    def task_read(self, task_id: int) -> JsonObject: ...

    def task_create(
        self,
        title: str,
        description: str | None,
        priority: str | None,
        due: str | None,
        project: str | None,
    ) -> JsonObject: ...

    def task_update(
        self, task_id: int, expected_version: int, changes: TaskChanges
    ) -> JsonObject: ...

    def task_set_status(
        self, task_id: int, status: str, reason: str | None, expected_version: int
    ) -> JsonObject: ...

    def task_note_add(self, task_id: int, body: str) -> JsonObject: ...

    def task_link_session(self, task_id: int) -> JsonObject: ...
