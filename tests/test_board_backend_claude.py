"""`LaunchClaude` through the dashboard backend, with a fake `claude`."""

import stat
from pathlib import Path

import pytest

from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import LaunchClaude
from meute.core.errors import MeuteError
from meute.core.session import AgentKind
from meute.tmux.layout import ensure_layout
from meute.tmux.names import MAIN_SESSION
from meute.tmux.panes import list_panes
from test_board_backend import _SPEC, ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixtures reused


def test_launch_claude_shows_the_new_session(ctx: CliContext, env: TmuxEnv, tmp_path: Path) -> None:  # noqa: F811 — fixture
    fake = tmp_path / "bin"
    fake.mkdir()
    script = fake / "claude"
    script.write_text("#!/bin/sh\nexec sleep 3600\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    ensure_layout(env.tmux, _SPEC)
    backend = CliBoardBackend(ctx, env, {"PATH": str(fake)})
    try:
        backend.perform(LaunchClaude(cwd=tmp_path, repo_id=None))
        data = backend.load()
    finally:
        backend.close()  # reaps the background `claude agents` run
    assert data is not None
    (row,) = data.sessions
    assert row.session.agent is AgentKind.CLAUDE
    (pane,) = (p for p in list_panes(env.tmux) if p.meute_id == row.session.id)
    assert pane.session == MAIN_SESSION


def test_launch_claude_without_claude_is_a_meute_error(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    backend = CliBoardBackend(ctx, env, {"PATH": str(tmp_path)})
    try:
        with pytest.raises(MeuteError, match=r"^claude not found: "):
            backend.perform(LaunchClaude(cwd=tmp_path, repo_id=None))
    finally:
        backend.close()
