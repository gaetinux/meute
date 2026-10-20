"""The Sessions view of the dashboard: folding, filters, quotas, details, clicks and detach."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from textual import events
from textual.color import Color
from textual.containers import VerticalScroll
from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_sessions import board_sessions, line_info
from meute.core.board_view import (
    BoardData,
    Detach,
    LaunchBash,
    LaunchClaude,
    SessionRow,
    ShowSession,
)
from meute.core.claude_session import ClaudeDetails
from meute.core.project import RepoId
from meute.core.quota_view import QuotaLine
from meute.core.session import SessionId
from meute.core.session_details import details_card
from meute.core.session_state import Exited, PermissionRequested, Running, SessionState
from meute.core.sessions_view import HeaderLine, RepoLine, SessionLine, ViewState
from meute.core.statusline import StatuslineData
from meute.core.styled import plain
from meute.tui.board import BoardApp, BoardOptions
from meute.tui.sessions_pane import SELECTED_STYLE
from support import (
    BOARD_AT,
    BOARD_HOME,
    BOARD_ID_A,
    BOARD_ID_B,
    BOARD_REPO_1,
    BOARD_REPO_2,
    board_data,
    board_session,
    selected_row,
)
from test_tui_board import FakeBackend, SnapCompare

_SIZE = (60, 30)
_NO_POLL = 3600.0
_NOW = BOARD_AT + timedelta(minutes=20)
_ID_C = SessionId("33333333-3333-4333-8333-333333333333")


def _row(session_id: SessionId, title: str, state: SessionState, repo: int | None) -> SessionRow:
    repo_id = None if repo is None else RepoId(repo)
    session = board_session(session_id, title, BOARD_HOME / "git" / title, repo_id, exited=False)
    return SessionRow(session=replace(session, state=state), has_pane=True, displayed=False)


def _rich_data() -> BoardData:
    """Two groups (meute, notes), one session asking for a permission, one ended, quotas."""
    return BoardData(
        sessions=(
            _row(BOARD_ID_A, "build", Running(), 1),
            _row(BOARD_ID_B, "review", PermissionRequested(), 2),
            _row(_ID_C, "old", Exited(code=0), 1),
        ),
        repos=(BOARD_REPO_1, BOARD_REPO_2),
        orphans=(),
        home=BOARD_HOME,
        details={
            BOARD_ID_A: ClaudeDetails(permission_mode="auto", model="opus", last_tool="Bash"),
            BOARD_ID_B: ClaudeDetails(permission_mode="plan", pending_permission="Bash(rm -rf x)"),
        },
        metrics={BOARD_ID_A: StatuslineData(context_pct=42.0, cost_usd=1.5, duration_ms=600_000)},
        quota=QuotaLine(
            five_hour_pct=85.0,
            five_hour_resets_at=datetime(2026, 10, 18, 12, 0, tzinfo=UTC),
            seven_day_pct=55.0,
            seven_day_resets_at=datetime(2026, 10, 20, 9, 0, tzinfo=UTC),
            limit_at=datetime(2026, 10, 18, 10, 30, tzinfo=UTC),
            peak="OFF-PEAK (weekend)",
        ),
        now=_NOW,
    )


def _calm_data() -> BoardData:
    """`_rich_data()` with "review" running: no session needs attention, no "Needs you"."""
    rich = _rich_data()
    review = rich.sessions[1]
    calm = replace(review, session=replace(review.session, state=Running()))
    return replace(rich, sessions=(rich.sessions[0], calm, rich.sessions[2]))


def _content(app: BoardApp, widget_id: str) -> Content:
    content = app.query_one(f"#{widget_id}", Static).content
    assert isinstance(content, Content)
    return content


def _colours_parse(content: Content) -> bool:
    """Tell whether every colour of the spans is one Textual knows (it ignores the others)."""
    words = {"bold", "reverse", "on", "underline"}
    for span in content.spans:
        for token in str(span.style).split():
            if token not in words:
                _ = Color.parse(token)  # raises ColorParseError
    return True


def _selected(app: BoardApp) -> list[str]:
    content = _content(app, "board")
    return selected_row(content, (SELECTED_STYLE,))


def _line_y(
    data: BoardData, wanted: Callable[[object], bool], state: ViewState | None = None
) -> int:
    lines = board_sessions(data, state or ViewState()).view.lines
    return next(i for i, line in enumerate(lines) if wanted(line))


def _scenario(
    data: BoardData,
    steps: Callable[[Pilot[None], BoardApp], Awaitable[None]],
    *,
    show_details: bool = True,
) -> FakeBackend:
    backend = FakeBackend(data)
    options = BoardOptions(show_details=show_details, local=UTC)
    app = BoardApp(backend, options, poll_seconds=_NO_POLL)

    async def run() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await steps(pilot, app)

    asyncio.run(run())
    return backend


def _is_session(session_id: SessionId) -> Callable[[object], bool]:
    return lambda line: isinstance(line, SessionLine) and line.session_id == session_id


def _is_header(group: str) -> Callable[[object], bool]:
    return lambda line: isinstance(line, HeaderLine) and line.group == group


def test_a_shows_only_the_sessions_that_need_attention() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        assert "build" in _content(app, "board").plain
        await pilot.press("a")
        board = _content(app, "board").plain
        assert "build" not in board
        assert "review" in board
        assert _selected(app) == [line for line in board.splitlines() if "review" in line]
        await pilot.press("a")
        assert "build" in _content(app, "board").plain

    _ = _scenario(_rich_data(), steps)


def test_e_shows_the_ended_sessions() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        board = _content(app, "board").plain
        assert "1 ended (e to show)" in board
        assert "old" not in board
        await pilot.press("e")
        board = _content(app, "board").plain
        assert "old  exited (0)" in board
        assert "ended (e to show)" not in board

    _ = _scenario(_rich_data(), steps)


def test_e_shows_the_recently_ended_sessions_without_a_pane() -> None:
    gone = SessionRow(
        session=_row(_ID_C, "gone", Exited(code=1), 1).session,
        has_pane=False,
        displayed=False,
    )
    data = replace(_rich_data(), sessions=_rich_data().sessions[:2], ended=(gone,))

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        assert "1 ended (e to show)" in _content(app, "board").plain
        await pilot.press("e")
        assert "gone  exited (1)" in _content(app, "board").plain

    _ = _scenario(data, steps)


def test_click_after_scrolling_hits_the_line_under_the_mouse() -> None:
    many = tuple(
        _row(SessionId(f"{n:08d}-1111-4111-8111-111111111111"), f"s{n}", Running(), None)
        for n in range(40)
    )
    data = replace(board_data(), sessions=many, now=_NOW)
    y = _line_y(data, _is_session(many[35].session.id))

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press(*["down"] * 39)
        await pilot.pause()
        assert app.query_one("#sessions", VerticalScroll).scroll_y > 0
        assert await pilot.click("#board", offset=(3, y))

    actions = _scenario(data, steps).actions
    assert actions == [ShowSession(session_id=many[35].session.id)]


def test_space_folds_the_selected_group_then_unfolds_it() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("space")
        board = _content(app, "board").plain
        assert "build" not in board
        assert _selected(app) == [line for line in board.splitlines() if "▶ " in line]
        assert _selected(app)[0].startswith("▶ meute")
        await pilot.press("space")
        assert "build" in _content(app, "board").plain
        assert "build" in _selected(app)[0]

    _ = _scenario(_calm_data(), steps)


def test_left_folds_and_right_unfolds() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("left", "left")
        assert "▶ " in _selected(app)[0]
        await pilot.press("right", "right")
        assert "build" in _selected(app)[0]

    _ = _scenario(_calm_data(), steps)


def test_keys_skip_headers_and_info_lines() -> None:
    data = _rich_data()

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        seen: list[str] = []
        for _ in range(6):
            seen += _selected(app)
            await pilot.press("down")
        for _ in range(6):
            await pilot.press("up")
            seen += _selected(app)
        assert seen
        assert all(text.lstrip(" ▶!●○").startswith(("build", "review", "notes")) for text in seen)

    _ = _scenario(data, steps)


def test_q_detaches() -> None:
    async def steps(pilot: Pilot[None], _app: BoardApp) -> None:
        await pilot.press("q")

    assert _scenario(_rich_data(), steps).actions == [Detach()]


def test_n_and_c_on_a_session_launch_in_its_repository() -> None:
    async def steps(pilot: Pilot[None], _app: BoardApp) -> None:
        await pilot.press("n", "c")

    cwd = BOARD_HOME / "git" / "build"
    assert _scenario(_calm_data(), steps).actions == [
        LaunchBash(cwd=cwd, repo_id=RepoId(1)),
        LaunchClaude(cwd=cwd, repo_id=RepoId(1)),
    ]


def test_enter_on_a_folded_group_unfolds_it() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("space", "enter")
        assert "build" in _content(app, "board").plain

    assert _scenario(_calm_data(), steps).actions == []


def test_click_on_a_session_selects_and_shows_it() -> None:
    data = _rich_data()
    y = _line_y(data, _is_session(BOARD_ID_B))

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        assert await pilot.click("#board", offset=(3, y))
        assert "review" in _selected(app)[0]

    assert _scenario(data, steps).actions == [ShowSession(session_id=BOARD_ID_B)]


def test_click_on_a_repository_only_selects_it() -> None:
    data = replace(
        _rich_data(), repos=(*_rich_data().repos, replace(BOARD_REPO_2, id=RepoId(3), name="idle"))
    )
    y = _line_y(data, lambda line: isinstance(line, RepoLine))

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        assert await pilot.click("#board", offset=(3, y))
        assert _selected(app)[0].startswith("  idle")

    assert _scenario(data, steps).actions == []


def test_click_on_a_header_folds_and_unfolds_its_group() -> None:
    data = _calm_data()
    y = _line_y(data, _is_header("notes"))

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        assert await pilot.click("#board", offset=(3, y))
        board = _content(app, "board").plain
        assert "review" not in board
        assert "build" in _selected(app)[0]  # the selection stays where it was
        assert await pilot.click("#board", offset=(3, y))
        assert "review" in _content(app, "board").plain

    assert _scenario(data, steps).actions == []


def test_click_outside_the_lines_does_nothing() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        lines = len(_content(app, "board").plain.splitlines())
        _ = await pilot.click("#board", offset=(3, lines + 2))
        assert "build" in _selected(app)[0]

    assert _scenario(_calm_data(), steps).actions == []


def test_details_follow_the_selection() -> None:
    data = _calm_data()
    model = board_sessions(data, ViewState())

    def expected(session_id: SessionId) -> str:
        info = line_info(model, _line_y(data, _is_session(session_id)))
        assert info is not None
        return "\n".join(plain(row) for row in details_card(info, home=BOARD_HOME, width=_SIZE[0]))

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        details = app.query_one("#details", Static)
        assert _content(app, "details").plain == expected(BOARD_ID_A)
        assert details.display
        await pilot.press("down")
        assert _content(app, "details").plain == expected(BOARD_ID_B)
        assert "Waiting for Bash(rm -rf x)" in _content(app, "details").plain

    _ = _scenario(data, steps)


def test_details_are_hidden_on_a_repository_and_when_disabled() -> None:
    async def on_repo(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("j", "j")
        assert _selected(app) == [
            line
            for line in _content(app, "board").plain.splitlines()
            if line.startswith("  meute (rust)")
        ]
        assert not app.query_one("#details", Static).display

    _ = _scenario(board_data(), on_repo)

    async def disabled(_pilot: Pilot[None], app: BoardApp) -> None:
        assert not app.query_one("#details", Static).display

    _ = _scenario(_rich_data(), disabled, show_details=False)


def test_quota_lines_are_bars_coloured_by_level() -> None:
    async def steps(_pilot: Pilot[None], app: BoardApp) -> None:
        quota = _content(app, "quota")
        assert quota.plain.splitlines() == [
            "5h ████████░░ 85%  resets 12:00 · limit ~10:30",
            "7d ██████░░░░ 55%  resets Tue 09:00 · OFF-PEAK (weekend)",
        ]
        styled = {quota.plain[s.start : s.end]: str(s.style) for s in quota.spans}
        assert styled["████████░░ 85%"] == "bold #f16c6c"
        assert styled["██████░░░░ 55%"] == "#e5c07b"
        assert _colours_parse(quota)

    _ = _scenario(_rich_data(), steps)


def test_low_quota_is_green_and_no_quota_hides_the_lines() -> None:
    low = replace(
        _rich_data(),
        quota=QuotaLine(
            five_hour_pct=10.0,
            five_hour_resets_at=None,
            seven_day_pct=None,
            seven_day_resets_at=None,
            limit_at=None,
            peak="",
        ),
    )

    async def steps(_pilot: Pilot[None], app: BoardApp) -> None:
        quota = _content(app, "quota")
        assert quota.plain == "5h █░░░░░░░░░ 10%"
        assert "#23d18b" in [str(s.style) for s in quota.spans]
        assert _colours_parse(quota)

    _ = _scenario(low, steps)

    async def none(_pilot: Pilot[None], app: BoardApp) -> None:
        assert not app.query_one("#quota", Static).display

    _ = _scenario(replace(_rich_data(), quota=None), none)


def test_risky_permission_mode_is_orange() -> None:
    async def steps(_pilot: Pilot[None], app: BoardApp) -> None:
        board = _content(app, "board")
        orange = [board.plain[s.start : s.end] for s in board.spans if s.style == "#e8912d"]
        assert orange == ["auto"]
        assert _colours_parse(board)

    _ = _scenario(_rich_data(), steps)


def test_mouse_wheel_scrolls_the_list() -> None:
    many = tuple(
        _row(SessionId(f"{n:08d}-1111-4111-8111-111111111111"), f"s{n}", Running(), None)
        for n in range(40)
    )
    data = replace(board_data(), sessions=many, now=_NOW)

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        sessions = app.query_one("#sessions", VerticalScroll)
        assert sessions.scroll_y == 0
        x, y = sessions.region.x + 2, sessions.region.y + 2
        app.screen.post_message(
            events.MouseScrollDown(None, x, y, 0, 1, 0, False, False, False, screen_x=x, screen_y=y)  # noqa: FBT003 — Textual's positional event fields
        )
        await pilot.pause(0.1)
        assert sessions.scroll_y > 0

    _ = _scenario(data, steps)


def _app(data: BoardData) -> BoardApp:
    return BoardApp(FakeBackend(data), BoardOptions(local=UTC), poll_seconds=_NO_POLL)


def test_sessions_60_columns(snap_compare: SnapCompare) -> None:
    assert snap_compare(_app(_rich_data()), terminal_size=(60, 30))


def test_sessions_100_columns(snap_compare: SnapCompare) -> None:
    assert snap_compare(_app(_rich_data()), press=["down"], terminal_size=(100, 30))
