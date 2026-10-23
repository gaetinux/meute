"""The names Claude sees agree, and the command written into `mcp.json` really serves them."""

import asyncio
import sys
from datetime import UTC
from pathlib import Path

from mcp import Client, ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from meute.claude.mcp_config import mcp_config_document, write_mcp_config
from meute.claude.settings import MEUTE_TOOLS
from meute.cli.mcp_backend import CliMcpBackend
from meute.cli.tmux_env import meute_command
from meute.core.json_types import JsonValue
from meute.core.paths import Paths
from meute.core.session import SessionId
from meute.mcp.server import build_server
from support import FIXED, load_json

SESSION = SessionId("0b9c1f0e-5f6a-4a43-9d57-5a3f0a1f7c11")


def _ignore(_error: BaseException) -> None:
    return


def _registered(tmp_path: Path) -> tuple[str, list[str]]:
    """The name and the tools of the server `build_server` builds, as a client sees them."""
    paths = Paths.from_roots(
        config_home=tmp_path / "c", data_home=tmp_path / "d", state_home=tmp_path / "s"
    )
    server = build_server(CliMcpBackend(paths, None, lambda: FIXED, UTC), on_unexpected=_ignore)

    async def go() -> tuple[str, list[str]]:
        async with Client(server) as client:
            info = client.server_info
            assert info is not None
            return info.name, [tool.name for tool in (await client.list_tools()).tools]

    return asyncio.run(go())


def test_the_allowed_tools_are_the_tools_of_the_server(tmp_path: Path) -> None:
    name, tools = _registered(tmp_path)
    assert tuple(f"mcp__{name}__{tool}" for tool in tools) == MEUTE_TOOLS


def test_the_configured_server_key_is_the_server_name(tmp_path: Path) -> None:
    name, _ = _registered(tmp_path)
    servers = mcp_config_document(meute_command(), SESSION)["mcpServers"]
    assert isinstance(servers, dict)
    assert list(servers) == [name]


def _strings(value: JsonValue) -> list[str]:
    assert isinstance(value, list)
    return [str(item) for item in value]


def test_the_command_written_into_mcp_json_serves_the_tools(tmp_path: Path) -> None:
    folder = tmp_path / "repo"  # the session's folder, where Claude starts the server
    marker = tmp_path / "shadowed.txt"
    for package in ("anyio", "pydantic", "typer"):
        (folder / package).mkdir(parents=True)
        (folder / package / "__init__.py").write_text(
            f"open({str(marker)!r}, 'a').write({package!r})\n", encoding="utf-8"
        )
    written = write_mcp_config(tmp_path / "state/meute", SESSION, meute_command())
    document = load_json(written.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    servers = document["mcpServers"]
    assert isinstance(servers, dict)
    entry = servers["meute"]
    assert isinstance(entry, dict)
    env = entry["env"]
    assert isinstance(env, dict)
    command = entry["command"]
    assert isinstance(command, str)
    params = StdioServerParameters(
        command=command,
        args=_strings(entry["args"]),
        env={
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            **{key: str(value) for key, value in env.items()},
        },
        cwd=folder,
    )
    errors = tmp_path / "server-stderr.txt"

    async def go() -> tuple[str, list[str]]:
        with errors.open("w", encoding="utf-8") as errlog:
            async with (
                stdio_client(params, errlog=errlog) as (read, write),
                ClientSession(read, write) as session,
            ):
                initialized = await session.initialize()
                listed = await session.list_tools()
        return initialized.server_info.name, [tool.name for tool in listed.tools]

    name, tools = asyncio.run(go())
    assert not marker.exists()
    assert command == sys.executable
    assert tuple(f"mcp__{name}__{tool}" for tool in tools) == MEUTE_TOOLS
    assert errors.read_text(encoding="utf-8") == ""
