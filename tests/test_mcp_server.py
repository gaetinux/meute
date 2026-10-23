"""Tests of the MCP server: tools seen through the SDK's in-memory client, over a fake backend."""

import asyncio
import json
from dataclasses import dataclass, field, replace

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent
from syrupy.assertion import SnapshotAssertion

from meute.core.errors import NotFound, VersionConflict
from meute.core.json_types import JsonObject, JsonValue
from meute.core.task import KEEP
from meute.mcp.backend import TaskChanges
from meute.mcp.server import build_server
from support import make_task

type Call = tuple[object, ...]

ANSWER: JsonObject = {"answer": "é", "n": 1}


@dataclass
class FakeBackend:
    """Record each call, then raise `error` or return `answer`."""

    answer: JsonValue = field(default_factory=lambda: dict(ANSWER))
    error: Exception | None = None
    calls: list[Call] = field(default_factory=list[Call])

    def _record(self, *call: object) -> JsonValue:
        self.calls.append(call)
        if self.error is not None:
            raise self.error
        return self.answer

    def _record_object(self, *call: object) -> JsonObject:
        answer = self._record(*call)
        return answer if isinstance(answer, dict) else {}

    def task_list(
        self,
        project: str | None,
        status: str | None,
        due: str | None,
        include_done: bool,  # noqa: FBT001 — signature fixed by McpBackend
    ) -> JsonValue:
        return self._record("task_list", project, status, due, include_done)

    def task_read(self, task_id: int) -> JsonObject:
        return self._record_object("task_read", task_id)

    def task_create(
        self,
        title: str,
        description: str | None,
        priority: str | None,
        due: str | None,
        project: str | None,
    ) -> JsonObject:
        return self._record_object("task_create", title, description, priority, due, project)

    def task_update(self, task_id: int, expected_version: int, changes: TaskChanges) -> JsonObject:
        return self._record_object("task_update", task_id, expected_version, changes)

    def task_set_status(
        self, task_id: int, status: str, reason: str | None, expected_version: int
    ) -> JsonObject:
        return self._record_object("task_set_status", task_id, status, reason, expected_version)

    def task_note_add(self, task_id: int, body: str) -> JsonObject:
        return self._record_object("task_note_add", task_id, body)

    def task_link_session(self, task_id: int) -> JsonObject:
        return self._record_object("task_link_session", task_id)


@dataclass
class Journal:
    errors: list[BaseException] = field(default_factory=list[BaseException])

    def __call__(self, error: BaseException) -> None:
        self.errors.append(error)


def serve(backend: FakeBackend, journal: Journal | None = None) -> MCPServer:
    return build_server(backend, on_unexpected=journal or Journal())


def call(server: MCPServer, name: str, arguments: dict[str, object]) -> CallToolResult:
    async def go() -> CallToolResult:
        async with Client(server) as client:
            return await client.call_tool(name, dict(arguments))

    return asyncio.run(go())


def text_of(result: CallToolResult) -> str:
    [block] = result.content
    assert isinstance(block, TextContent)
    return block.text


def test_the_tools_list_gives_names_descriptions_and_schemas(snapshot: SnapshotAssertion) -> None:
    async def go() -> str:
        async with Client(serve(FakeBackend())) as client:
            tools = (await client.list_tools()).tools
        dumped = [tool.model_dump_json(by_alias=True, exclude_none=True) for tool in tools]
        return "\n".join(json.dumps(json.loads(line), indent=2) for line in dumped)

    assert asyncio.run(go()) == snapshot


CHANGES_KEPT = TaskChanges(title=KEEP, description=KEEP, priority=KEEP, due=KEEP, project=KEEP)


@pytest.mark.parametrize(
    ("name", "arguments", "expected"),
    [
        ("task_list", {}, ("task_list", None, None, None, False)),
        (
            "task_list",
            {"project": "web", "status": "todo", "due": "week", "include_done": True},
            ("task_list", "web", "todo", "week", True),
        ),
        ("task_read", {"id": 3}, ("task_read", 3)),
        ("task_create", {"title": "Fix"}, ("task_create", "Fix", None, None, None, None)),
        (
            "task_create",
            {
                "title": "Fix",
                "description": "d",
                "priority": "high",
                "due": "2026-10-30",
                "project": "web",
            },
            ("task_create", "Fix", "d", "high", "2026-10-30", "web"),
        ),
        ("task_update", {"id": 3, "expected_version": 2}, ("task_update", 3, 2, CHANGES_KEPT)),
        (
            "task_update",
            {"id": 3, "expected_version": 2, "title": "New", "due": None, "project": None},
            ("task_update", 3, 2, replace(CHANGES_KEPT, title="New", due=None, project=None)),
        ),
        (
            "task_update",
            {"id": 3, "expected_version": 2, "description": "", "priority": "low", "due": "x"},
            ("task_update", 3, 2, replace(CHANGES_KEPT, description="", priority="low", due="x")),
        ),
        (
            "task_set_status",
            {"id": 3, "status": "blocked", "reason": "waiting", "expected_version": 4},
            ("task_set_status", 3, "blocked", "waiting", 4),
        ),
        (
            "task_set_status",
            {"id": 3, "status": "done", "expected_version": 4},
            ("task_set_status", 3, "done", None, 4),
        ),
        ("task_note_add", {"id": 3, "body": "progress"}, ("task_note_add", 3, "progress")),
        ("task_link_session", {"id": 3}, ("task_link_session", 3)),
    ],
)
def test_each_tool_calls_its_backend_method_and_answers_its_json(
    name: str, arguments: dict[str, object], expected: Call
) -> None:
    backend = FakeBackend()
    result = call(serve(backend), name, arguments)
    assert backend.calls == [expected]
    assert not result.is_error
    assert json.loads(text_of(result)) == ANSWER


def test_a_list_answer_stays_one_json_array() -> None:
    backend = FakeBackend(answer=[{"id": 1}, {"id": 2}])
    result = call(serve(backend), "task_list", {})
    assert json.loads(text_of(result)) == [{"id": 1}, {"id": 2}]


def test_a_meute_error_becomes_a_tool_error_with_its_exact_message() -> None:
    backend = FakeBackend(error=NotFound("task", "#9"))
    result = call(serve(backend), "task_read", {"id": 9})
    assert result.is_error
    assert text_of(result) == "task not found: #9"


def test_a_version_conflict_gives_the_current_version() -> None:
    backend = FakeBackend(error=VersionConflict(replace(make_task(3), version=7)))
    result = call(serve(backend), "task_update", {"id": 3, "expected_version": 2, "title": "x"})
    assert result.is_error
    assert "current version: 7" in text_of(result)


def test_an_unexpected_error_is_journaled_and_answered_as_internal_error() -> None:
    error = RuntimeError("secret detail")
    journal = Journal()
    result = call(serve(FakeBackend(error=error), journal), "task_note_add", {"id": 1, "body": "b"})
    assert result.is_error
    assert text_of(result) == "internal error"
    assert journal.errors == [error]


def test_a_meute_error_is_not_journaled() -> None:
    journal = Journal()
    call(serve(FakeBackend(error=NotFound("task", "#9")), journal), "task_read", {"id": 9})
    assert journal.errors == []


@pytest.mark.parametrize("bad_id", ["x", "", 1.5, None, [1], {"id": 1}])
@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("task_read", {}),
        ("task_update", {"expected_version": 1}),
        ("task_set_status", {"status": "done", "expected_version": 1}),
        ("task_note_add", {"body": "b"}),
        ("task_link_session", {}),
    ],
)
def test_an_id_that_is_not_an_integer_is_refused_without_calling_the_backend(
    name: str, arguments: dict[str, object], bad_id: object
) -> None:
    backend = FakeBackend()
    result = call(serve(backend), name, {**arguments, "id": bad_id})
    assert result.is_error
    assert backend.calls == []


@pytest.mark.parametrize("bad_version", ["x", 2.5, None, [2]])
def test_an_expected_version_that_is_not_an_integer_is_refused(bad_version: object) -> None:
    backend = FakeBackend()
    result = call(serve(backend), "task_update", {"id": 1, "expected_version": bad_version})
    assert result.is_error
    assert backend.calls == []


def test_a_missing_id_is_refused_without_calling_the_backend() -> None:
    backend = FakeBackend()
    result = call(serve(backend), "task_read", {})
    assert result.is_error
    assert backend.calls == []
