"""The Sessions view in colour: roles to styles, band and selection, tabs, quotas, details."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from textual import events
from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_header import Tab, tabs_line
from meute.core.board_sessions import board_sessions, line_info
from meute.core.board_view import BoardData, SessionRow
from meute.core.claude_session import ClaudeDetails
from meute.core.config_validate import Config
from meute.core.quota_view import QuotaLine
from meute.core.session import SessionId
from meute.core.session_state import PermissionRequested, Running
from meute.core.sessions_view import SessionLine, ViewState
from meute.core.statusline import StatuslineData
from meute.core.styled import Role, Span
from meute.tui.board import BoardApp, BoardOptions
from meute.tui.sessions_pane import (
    BAND_STYLE,
    BLURRED_SELECTED_STYLE,
    ROLE_STYLES,
    SELECTED_STYLE,
    details_content,
    styled_content,
    tabs_content,
    view_content,
)
from support import BOARD_AT, BOARD_HOME, board_session
from test_tui_board import FakeBackend, SnapCompare

_NOW = BOARD_AT + timedelta(minutes=20)
_ID_A = SessionId("00000001-1111-4111-8111-111111111111")
_ID_B = SessionId("00000002-1111-4111-8111-111111111111")
_NO_POLL = 3600.0


def _row(session_id: SessionId, title: str, state: Running | PermissionRequested) -> SessionRow:
    base = board_session(session_id, title, BOARD_HOME / "git" / title, None, exited=False)
    session = replace(base, state=state, last_activity_at=_NOW - timedelta(minutes=4))
    return SessionRow(session=session, has_pane=True, displayed=session_id == _ID_A)


def _data() -> BoardData:
    return BoardData(
        sessions=(
            _row(_ID_A, "build", Running()),
            _row(_ID_B, "review", PermissionRequested()),
        ),
        repos=(),
        orphans=(),
        home=BOARD_HOME,
        details={
            _ID_A: ClaudeDetails(permission_mode="auto", model="opus", last_tool="Bash"),
            _ID_B: ClaudeDetails(
                permission_mode="plan", pending_permission="Bash(rm -rf x)", last_message="Done?"
            ),
        },
        metrics={
            _ID_A: StatuslineData(
                duration_ms=3_660_000, cost_usd=3.8, context_pct=41.0, worktree_branch="feat/x"
            ),
            _ID_B: StatuslineData(duration_ms=420_000, cost_usd=0.19, context_pct=3.0),
        },
        quota=QuotaLine(
            five_hour_pct=62.0,
            five_hour_resets_at=datetime(2026, 10, 18, 12, 0, tzinfo=UTC),
            seven_day_pct=28.0,
            seven_day_resets_at=datetime(2026, 10, 20, 9, 0, tzinfo=UTC),
            limit_at=None,
            peak="✦ OFF-PEAK (weekend)",
        ),
        now=_NOW,
    )


def _styled(content: Content) -> list[tuple[str, str]]:
    return [(content.plain[s.start : s.end], str(s.style)) for s in content.spans]


def test_a_risky_segment_gets_the_orange_style() -> None:
    content = styled_content((Span("mode ", Role.DIM), Span("auto", Role.RISKY)))
    assert content.plain == "mode auto"
    assert ("auto", "#e8912d") in _styled(content)
    assert ("mode ", "#8a8a8a") in _styled(content)


def test_every_role_has_a_style() -> None:
    assert set(ROLE_STYLES) == set(Role)


def test_a_selected_band_line_carries_the_selection_not_the_red_background() -> None:
    board = board_sessions(_data(), ViewState())
    lines = [line.text for line in board.view.lines]
    card = next(
        i for i, ln in enumerate(board.view.lines) if isinstance(ln, SessionLine) and ln.band
    )
    plain = view_content(board, -1)
    assert BAND_STYLE in [style for _, style in _styled(plain.split("\n")[card])]
    selected = view_content(board, card).split("\n")[card]
    styles = [style for _, style in _styled(selected)]
    assert SELECTED_STYLE in styles
    assert BAND_STYLE not in styles
    assert lines[card].startswith("  ! review")


def test_the_selection_covers_the_three_lines_of_a_card() -> None:
    board = board_sessions(_data(), ViewState())
    first = next(
        i for i, ln in enumerate(board.view.lines) if isinstance(ln, SessionLine) and not ln.band
    )
    rows = view_content(board, first, focused=True).split("\n")
    covered = [i for i, row in enumerate(rows) if SELECTED_STYLE in [s for _, s in _styled(row)]]
    assert covered == [first, first + 1, first + 2]
    blurred = view_content(board, first, focused=False).split("\n")
    grey = [
        i for i, row in enumerate(blurred) if BLURRED_SELECTED_STYLE in [s for _, s in _styled(row)]
    ]
    assert grey == covered


def test_the_active_tab_is_underlined_without_the_focus() -> None:
    line = tabs_line(Tab.SESSIONS, overdue=0, totals="2 live", width=40)
    focused = _styled(tabs_content(line, focused=True))
    blurred = _styled(tabs_content(line, focused=False))
    assert (" Sessions ", ROLE_STYLES[Role.TAB_ACTIVE]) in focused
    assert (" Sessions ", f"{ROLE_STYLES[Role.TAB]} underline") in blurred


def test_details_open_with_a_rule_and_keep_three_rows() -> None:
    board = board_sessions(_data(), ViewState())
    index = next(
        i for i, ln in enumerate(board.view.lines) if isinstance(ln, SessionLine) and ln.band
    )
    info = line_info(board, index)
    assert info is not None
    content = details_content(board, info, width=40)
    rows = content.plain.split("\n")
    assert rows[0] == "─ review " + "─" * 31
    assert rows[1:] == [
        "Reply       Done?",
        "Folder      ~/git/review",
        "Waiting for Bash(rm -rf x)",
    ]
    assert ("─ review " + "─" * 31, ROLE_STYLES[Role.ACCENT]) in _styled(content)


def test_board_default_width_is_72() -> None:
    assert Config().ui.board_width == 72


def _app(data: BoardData) -> BoardApp:
    return BoardApp(FakeBackend(data), BoardOptions(local=UTC), poll_seconds=_NO_POLL)


def test_the_board_takes_its_width_from_the_widget() -> None:
    app = _app(_data())

    async def run() -> None:
        async with app.run_test(size=(50, 30)) as pilot:
            await pilot.pause()
            board = app.query_one("#board", Static).content
            assert isinstance(board, Content)
            assert max(len(line) for line in board.plain.split("\n")) <= 50

    asyncio.run(run())


def test_sessions_cards_72_columns(snap_compare: SnapCompare) -> None:
    assert snap_compare(_app(_data()), terminal_size=(72, 30))


def test_sessions_needs_you_100_columns(snap_compare: SnapCompare) -> None:
    assert snap_compare(_app(_data()), press=["down"], terminal_size=(100, 30))


def test_sessions_blurred_72_columns(snap_compare: SnapCompare) -> None:
    async def blur(pilot: Pilot[None]) -> None:
        pilot.app.post_message(events.AppBlur())
        await pilot.pause()

    assert snap_compare(_app(_data()), terminal_size=(72, 30), run_before=blur)
