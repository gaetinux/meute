"""What `CliBoardBackend` adds for the Sessions view: details, metrics, projects, quota, detach."""

import subprocess
import time
from datetime import timedelta
from pathlib import Path

from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import BoardData, Detach
from meute.core.claude_session import ClaudeDetails
from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.samples import record_metrics, record_quota
from meute.core.statusline import StatuslineData
from support import FIXED
from test_board_backend import _ENVIRON, _Clock, ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixtures reused
from tmux_support import TestServer


def _loaded(backend: CliBoardBackend) -> BoardData:
    data = backend.load()
    assert data is not None
    return data


def test_load_brings_details_metrics_projects_and_the_clock(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="trial"), _ENVIRON)
    with ctx.db.transaction() as conn:
        conn.execute(
            "UPDATE sessions SET agent = 'claude', permission_mode = 'auto' WHERE id = ?",
            (session.id,),
        )
    project = create_project(ctx.db, "Plan")
    _ = record_metrics(ctx.db, session.id, StatuslineData(context_pct=12.0))
    data = _loaded(CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock()))
    assert data.details == {session.id: ClaudeDetails(permission_mode="auto")}
    assert data.metrics == {session.id: StatuslineData(context_pct=12.0)}
    assert data.projects == {project.id: "Plan"}
    assert data.now == FIXED


def test_load_projects_the_quota_from_the_last_half_hour(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    resets = FIXED + timedelta(hours=2)
    for minutes, pct in ((40, 5.0), (20, 30.0), (10, 40.0)):
        with Database.open(
            tmp_path / "meute.db",
            busy_timeout_ms=1000,
            clock=lambda m=minutes: FIXED - timedelta(minutes=m),
        ) as other:
            _ = record_quota(
                other,
                StatuslineData(five_hour_pct=pct, five_hour_resets_at=resets, seven_day_pct=20.0),
            )
    quota = _loaded(CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())).quota
    assert quota is not None
    assert (quota.five_hour_pct, quota.five_hour_resets_at, quota.seven_day_pct) == (
        40.0,
        resets,
        20.0,
    )
    # 30 % then 40 % ten minutes later (the 5 % is older than 30 min): 100 % in 50 minutes.
    assert quota.limit_at == FIXED + timedelta(minutes=50)
    assert "PEAK" in quota.peak


def test_without_quota_samples_only_the_peak_hours_are_known(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
) -> None:
    quota = _loaded(CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())).quota
    assert quota is not None
    assert (quota.five_hour_pct, quota.seven_day_pct, quota.limit_at) == (None, None, None)
    assert quota.peak


def _clients(server: TestServer) -> str:
    return server.tmux.run("list-clients", "-F", "#{client_name}")


def test_detach_detaches_the_client(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmux_server: TestServer,
) -> None:
    client = subprocess.Popen(
        [*tmux_server.tmux.base_args(), "-C", "attach-session", "-t", "test"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while not _clients(tmux_server) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _clients(tmux_server)
        CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock()).perform(Detach())
        assert client.wait(timeout=10) == 0
        assert not _clients(tmux_server)
    finally:
        client.kill()
        _ = client.wait()
