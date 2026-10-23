"""`meute mcp` as a subprocess: the SDK's stdio client, and nothing but protocol on stdout."""

import asyncio
import json
import subprocess
import sys
import threading

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent

from conftest import Sandbox
from meute.core.json_types import JsonObject, JsonValue
from support import load_json

SESSION = "0b9c1f0e-5f6a-4a43-9d57-5a3f0a1f7c11"
TOOLS = [
    "task_list",
    "task_read",
    "task_create",
    "task_update",
    "task_set_status",
    "task_note_add",
    "task_link_session",
]


def server_env(box: Sandbox) -> dict[str, str]:
    return {
        "HOME": str(box.root / "home"),
        "XDG_CONFIG_HOME": str(box.root / "config"),
        "XDG_DATA_HOME": str(box.root / "data"),
        "XDG_STATE_HOME": str(box.root / "state"),
        "MEUTE_NOW": "2026-10-14T10:30[Europe/Paris]",
        "MEUTE_SESSION": SESSION,
        "PYTHONWARNINGS": "default",
    }


def test_the_sdk_client_lists_the_tools_and_reads_a_task(sandbox: Sandbox) -> None:
    assert sandbox.run("task", "add", "Write the report").returncode == 0
    errors = sandbox.root / "server-stderr.txt"
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "meute", "mcp"], env=server_env(sandbox)
    )

    async def go() -> tuple[str, list[str], str]:
        with errors.open("w", encoding="utf-8") as errlog:
            async with (
                stdio_client(params, errlog=errlog) as (read, write),
                ClientSession(read, write) as session,
            ):
                initialized = await session.initialize()
                listed = await session.list_tools()
                result = await session.call_tool("task_read", {"id": 1})
        [block] = result.content
        assert isinstance(block, TextContent)
        assert not result.is_error
        return initialized.server_info.name, [t.name for t in listed.tools], block.text

    name, tools, text = asyncio.run(go())
    assert name == "meute"
    assert tools == TOOLS
    task = as_object(load_json(text))
    assert (task["id"], task["title"], task["notes"]) == (1, "Write the report", [])
    assert errors.read_text(encoding="utf-8") == ""


def as_object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def answers_of(stdout: str) -> list[JsonObject]:
    return [as_object(load_json(line)) for line in stdout.splitlines()]


def jsonrpc(method: str, ident: int | None = None, **params: object) -> str:
    message: dict[str, object] = {"jsonrpc": "2.0", "method": method, "params": params}
    if ident is not None:
        message["id"] = ident
    return json.dumps(message) + "\n"


INITIALIZE = jsonrpc(
    "initialize",
    1,
    protocolVersion="2025-06-18",
    capabilities={},
    clientInfo={"name": "t", "version": "0"},
)
INITIALIZED = jsonrpc("notifications/initialized")


def converse(box: Sandbox, requests: list[str], answers: int) -> tuple[list[JsonObject], str]:
    """Send `requests`, read `answers` lines, then close stdin; return all of stdout and stderr."""
    with subprocess.Popen(
        [sys.executable, "-m", "meute", "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=server_env(box),
    ) as server:
        watchdog = threading.Timer(30, server.kill)
        watchdog.start()
        try:
            assert server.stdin is not None
            assert server.stdout is not None
            server.stdin.write("".join(requests))
            server.stdin.flush()
            lines = [server.stdout.readline() for _ in range(answers)]
            rest, stderr = server.communicate()
        finally:
            watchdog.cancel()
    return answers_of("".join(lines) + rest), stderr


def test_stdout_holds_only_protocol_and_the_database_is_not_touched_before_a_tool_call(
    sandbox: Sandbox,
) -> None:
    answers, stderr = converse(sandbox, [INITIALIZE, INITIALIZED, jsonrpc("tools/list", 2)], 2)
    assert [a["id"] for a in answers] == [1, 2]
    assert all(a["jsonrpc"] == "2.0" for a in answers)
    assert not (sandbox.root / "data").exists()
    assert not (sandbox.root / "state").exists()
    assert "Traceback" not in stderr


def test_a_tool_call_on_a_broken_database_answers_and_keeps_stdout_clean(
    sandbox: Sandbox,
) -> None:
    (sandbox.root / "data").write_text("not a folder", encoding="utf-8")
    call = jsonrpc("tools/call", 2, name="task_read", arguments={"id": 1})
    answers, _ = converse(sandbox, [INITIALIZE, INITIALIZED, call], 2)
    assert [a["id"] for a in answers] == [1, 2]
    result = as_object(answers[1]["result"])
    assert result["isError"] is True
    assert "meute database unavailable: " in str(result["content"])
