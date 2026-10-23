"""Ids and versions out of SQLite's range are refused as input, never an internal error."""

from collections.abc import Callable
from datetime import UTC
from pathlib import Path

import pytest

from meute.cli.mcp_backend import CliMcpBackend
from meute.core.errors import InvalidInput, NotFound
from meute.core.paths import Paths
from meute.core.session import SessionId
from meute.core.task import KEEP
from meute.mcp.backend import TaskChanges
from support import FIXED

SESSION = SessionId("0b9c1f0e-5f6a-4a43-9d57-5a3f0a1f7c11")
KEPT = TaskChanges(title=KEEP, description=KEEP, priority=KEEP, due=KEEP, project=KEEP)
INT64_MAX = 2**63 - 1


@pytest.fixture
def backend(tmp_path: Path) -> CliMcpBackend:
    paths = Paths.from_roots(
        config_home=tmp_path / "c", data_home=tmp_path / "d", state_home=tmp_path / "s"
    )
    return CliMcpBackend(paths, SESSION, lambda: FIXED, UTC)


type Call = Callable[[CliMcpBackend, int], object]


def _read(b: CliMcpBackend, i: int) -> object:
    return b.task_read(i)


def _update(b: CliMcpBackend, i: int) -> object:
    return b.task_update(i, 1, KEPT)


def _set_status(b: CliMcpBackend, i: int) -> object:
    return b.task_set_status(i, "todo", None, 1)


def _note_add(b: CliMcpBackend, i: int) -> object:
    return b.task_note_add(i, "n")


def _link_session(b: CliMcpBackend, i: int) -> object:
    return b.task_link_session(i)


@pytest.mark.parametrize("task_id", [0, -1, INT64_MAX + 1, 2**200])
@pytest.mark.parametrize("call", [_read, _update, _set_status, _note_add, _link_session])
def test_an_id_out_of_range_is_invalid_input(
    backend: CliMcpBackend, call: Call, task_id: int
) -> None:
    with pytest.raises(InvalidInput, match=rf"^id out of range: {task_id}$"):
        _ = call(backend, task_id)


@pytest.mark.parametrize("version", [INT64_MAX + 1, -(2**63) - 1])
def test_an_expected_version_out_of_range_is_invalid_input(
    backend: CliMcpBackend, version: int
) -> None:
    message = rf"^expected_version out of range: {version}$"
    with pytest.raises(InvalidInput, match=message):
        _ = backend.task_update(1, version, KEPT)
    with pytest.raises(InvalidInput, match=message):
        _ = backend.task_set_status(1, "todo", None, version)


def test_the_largest_id_is_looked_up(backend: CliMcpBackend) -> None:
    with pytest.raises(NotFound):
        _ = backend.task_read(INT64_MAX)
