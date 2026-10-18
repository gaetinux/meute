"""The board quota line and the tmux status line leave out windows that have reset."""

from datetime import timedelta
from pathlib import Path

from meute.cli.board_data import quota_line
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_show import show_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.samples import record_quota
from meute.core.statusline import StatuslineData
from meute.tmux.layout import ensure_layout
from support import FIXED
from test_board_backend import _ENVIRON, _SPEC, ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixtures reused

_STALE = StatuslineData(
    five_hour_pct=97,
    five_hour_resets_at=FIXED - timedelta(hours=1),
    seven_day_pct=61,
    seven_day_resets_at=FIXED + timedelta(days=2),
)


def test_board_quota_line_drops_a_window_that_has_reset(
    ctx: CliContext,  # noqa: F811 — fixture
) -> None:
    _ = record_quota(ctx.db, _STALE)
    line = quota_line(ctx, FIXED, _ENVIRON)
    assert (line.five_hour_pct, line.five_hour_resets_at) == (None, None)
    assert (line.seven_day_pct, line.seven_day_resets_at) == (61, _STALE.seven_day_resets_at)


def test_status_line_after_show_has_no_reset_window(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    _ = record_quota(ctx.db, _STALE)
    ensure_layout(env.tmux, _SPEC)
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="trial"), _ENVIRON)
    show_session(ctx, env, session.id)
    assert env.tmux.run("show-options", "-gv", "@meute_status") == "▶ trial"
