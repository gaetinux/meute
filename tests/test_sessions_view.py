"""Tests of the Sessions view model."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from meute.core.agents import AgentInfo
from meute.core.board_view import SessionRow
from meute.core.claude_session import ClaudeDetails
from meute.core.project import ProjectId, RepoId
from meute.core.repo import Repo
from meute.core.session import Session, SessionId
from meute.core.session_state import (
    Exited,
    Idle,
    MaybeStuck,
    PermissionRequested,
    Running,
    SessionState,
    WaitingInput,
)
from meute.core.sessions_view import (
    HeaderLine,
    InfoLine,
    RepoLine,
    SessionInfo,
    SessionLine,
    SessionsView,
    ViewLine,
    ViewState,
    build_view,
    details_lines,
    group_name,
    keep_selection,
    line_key,
    selectable,
)
from meute.core.statusline import StatuslineData
from support import BOARD_AT, BOARD_HOME, board_repo, board_session

_NOW = BOARD_AT + timedelta(hours=2)


def _id(number: int) -> SessionId:
    return SessionId(f"{number:08d}-1111-4111-8111-111111111111")


def _info(  # noqa: PLR0913 — a test builder
    number: int,
    title: str,
    state: SessionState,
    *,
    group: str = "alpha",
    age: timedelta = timedelta(minutes=5),
    details: ClaudeDetails | None = None,
    metrics: StatuslineData | None = None,
    repo_id: RepoId | None = None,
) -> SessionInfo:
    base = board_session(_id(number), title, BOARD_HOME / "git" / "x", repo_id, exited=False)
    session = replace(base, state=state, last_activity_at=_NOW - age)
    row = SessionRow(session=session, has_pane=True, displayed=False)
    return SessionInfo(row=row, details=details, metrics=metrics, group=group)


def _view(
    infos: list[SessionInfo],
    state: ViewState | None = None,
    *,
    repos: list[Repo] | None = None,
    outside: list[AgentInfo] | None = None,
    orphans: list[str] | None = None,
) -> SessionsView:
    return build_view(
        infos,
        repos or [],
        outside or [],
        orphans or [],
        state or ViewState(),
        now=_NOW,
        home=BOARD_HOME,
    )


def _texts(view: SessionsView) -> list[str]:
    return [line.text for line in view.lines]


_METRICS = StatuslineData(context_pct=42.0, cost_usd=1.234, duration_ms=3_900_000)
_DETAILS = ClaudeDetails(permission_mode="plan", model="opus", last_tool="Bash")


def _three_groups() -> list[SessionInfo]:
    return [
        _info(1, "build", Running(), group="zeta", metrics=_METRICS, details=_DETAILS),
        _info(2, "review", PermissionRequested(), group="Alpha"),
        _info(3, "scratch", Idle(), group="Other"),
        _info(4, "docs", WaitingInput(), group="alpha", age=timedelta(days=2)),
        _info(5, "old", Exited(code=0), group="zeta"),
        _info(6, "stuck one", MaybeStuck(), group="Alpha", age=timedelta(hours=3)),
    ]


def test_group_name_prefers_project_then_repo_then_other() -> None:
    projects = {ProjectId(1): "Plan"}
    repos = {RepoId(7): board_repo(7, "meute", None)}
    base = _info(1, "t", Idle()).row.session

    def name(session: Session) -> str:
        return group_name(session, projects=projects, repos=repos)

    assert name(replace(base, project_id=ProjectId(1), repo_id=RepoId(7))) == "Plan"
    assert name(replace(base, project_id=None, repo_id=RepoId(7))) == "meute"
    assert name(replace(base, project_id=None, repo_id=None)) == "Other"
    assert name(replace(base, project_id=ProjectId(9), repo_id=RepoId(8))) == "Other"
    assert name(replace(base, project_id=ProjectId(9), repo_id=RepoId(7))) == "meute"


def test_groups_sorted_without_case_other_last(snapshot: SnapshotAssertion) -> None:
    view = _view(_three_groups())
    headers = [line.group for line in view.lines if isinstance(line, HeaderLine)]
    assert headers == ["Alpha", "alpha", "zeta", "Other"]
    assert _texts(view) == snapshot


def test_header_text_sums_latest_metrics() -> None:
    infos = [
        _info(1, "a", Running(), metrics=_METRICS),
        _info(2, "b", Idle(), metrics=StatuslineData(cost_usd=0.5, duration_ms=600_000)),
        _info(3, "c", Exited(code=1)),
    ]
    assert _texts(_view(infos))[0] == "alpha  2 live · 1h15 · $1.73"


def test_header_omits_unknown_parts() -> None:
    assert _texts(_view([_info(1, "a", Idle())]))[0] == "alpha  1 live"
    only_duration = _info(1, "a", Idle(), metrics=StatuslineData(duration_ms=120_000))
    assert _texts(_view([only_duration]))[0] == "alpha  1 live · 2m"


def test_session_line_exact_text() -> None:
    info = _info(1, "build", Running(), metrics=_METRICS, details=_DETAILS)
    line = _view([info]).lines[1]
    assert line == SessionLine(
        session_id=_id(1),
        text="   build  running  5m  42%  $1.23  [plan]",
        attention=False,
    )


def test_session_line_marks_displayed_and_attention() -> None:
    info = _info(1, "ask", PermissionRequested())
    displayed = replace(info, row=replace(info.row, displayed=True))
    line = _view([displayed]).lines[1]
    assert isinstance(line, SessionLine)
    assert line.text == "▶ !ask  permission  5m"
    assert line.attention is True


def test_session_line_hides_small_cost_and_unknown_parts() -> None:
    cheap = _info(1, "t", Idle(), metrics=StatuslineData(cost_usd=0.10))
    assert _view([cheap]).lines[1].text == "   t  idle  5m"


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(seconds=59), "now"),
        (timedelta(seconds=-30), "now"),
        (timedelta(minutes=1), "1m"),
        (timedelta(minutes=59), "59m"),
        (timedelta(minutes=60), "1h"),
        (timedelta(hours=23), "23h"),
        (timedelta(hours=24), "1d"),
        (timedelta(days=9), "9d"),
    ],
)
def test_age_text(age: timedelta, expected: str) -> None:
    assert _view([_info(1, "t", Idle(), age=age)]).lines[1].text == f"   t  idle  {expected}"


def test_collapsed_group_shows_header_only() -> None:
    view = _view(_three_groups(), ViewState(collapsed=frozenset({"zeta"})))
    texts = _texts(view)
    assert "zeta  1 live · 1h05 · $1.23 (collapsed)" in texts
    assert not any("build" in text or "old" in text for text in texts)
    assert not any("ended" in text for text in texts)


def test_ended_sessions_hidden_then_shown(snapshot: SnapshotAssertion) -> None:
    infos = _three_groups()
    hidden = _view(infos)
    assert InfoLine("1 ended (e to show)") in hidden.lines
    assert not any("exited" in text for text in _texts(hidden))
    shown = _view(infos, ViewState(show_ended=True))
    assert not any(isinstance(line, InfoLine) and "ended" in line.text for line in shown.lines)
    assert any("exited (0)" in text for text in _texts(shown))
    assert _texts(shown) == snapshot


def test_attention_filter_keeps_attention_sessions_only(snapshot: SnapshotAssertion) -> None:
    view = _view(_three_groups(), ViewState(attention_only=True))
    sessions = [line for line in view.lines if isinstance(line, SessionLine)]
    assert {line.session_id for line in sessions} == {_id(2), _id(4), _id(6)}
    assert all(line.attention for line in sessions)
    headers = [line.group for line in view.lines if isinstance(line, HeaderLine)]
    assert headers == ["Alpha", "alpha"]
    assert _texts(view) == snapshot


def test_attention_filter_without_result() -> None:
    view = _view([_info(1, "a", Running())], ViewState(attention_only=True))
    assert view.lines == (InfoLine("Nothing needs your attention."),)


def test_repositories_without_live_session_and_bottom_sections(
    snapshot: SnapshotAssertion,
) -> None:
    repos = [board_repo(1, "meute", "rust"), board_repo(2, "notes", None), board_repo(3, "x", "go")]
    infos = [
        _info(1, "live", Idle(), repo_id=RepoId(1)),
        _info(2, "dead", Exited(code=1), repo_id=RepoId(2)),
    ]
    outside = [
        AgentInfo(pid=4, cwd="/home/me/w", kind="cli", session_id="s", name="ext", status="busy")
    ]
    view = _view(infos, repos=repos, outside=outside, orphans=["%7"])
    repo_lines = [line for line in view.lines if isinstance(line, RepoLine)]
    assert [line.repo_id for line in repo_lines] == [RepoId(2), RepoId(3)]
    assert _texts(view) == snapshot


def test_no_bottom_sections_when_empty() -> None:
    texts = _texts(_view([_info(1, "a", Idle())]))
    assert texts == ["alpha  1 live", "   a  idle  5m"]


def test_untrusted_text_is_neutralised() -> None:
    evil = _info(
        1,
        "t\x1b[2Jx",
        Idle(),
        group="g\x1b[2J",
        details=ClaudeDetails(
            last_message="m\x1b[2J",
            model="o\x1b[2J",
            pending_permission="p\x1b[2J",
            permission_mode="pm\x1b[2J",
            last_tool="lt\x1b[2J",
        ),
    )
    agent = AgentInfo(
        pid=1, cwd="/w\x1b[2J", kind="cli", session_id="s", name="n\x1b[2J", status="b\x1b[2J"
    )
    view = _view(
        [evil],
        repos=[board_repo(1, "r\x1b[2J", "k\x1b[2J")],
        orphans=["%\x1b[2J"],
        outside=[agent],
    )
    for text in [*_texts(view), *details_lines(evil, now=_NOW, home=BOARD_HOME)]:
        assert "\x1b" not in text


def test_selectable_and_line_key() -> None:
    repos = [board_repo(1, "meute", None)]
    view = _view([_info(1, "a", Idle()), _info(2, "b", Idle())], repos=repos)
    chosen = selectable(view)
    assert [type(view.lines[i]) for i in chosen] == [SessionLine, SessionLine, RepoLine]
    assert [line_key(view.lines[i]) for i in chosen] == [
        f"session:{_id(1)}",
        f"session:{_id(2)}",
        "repo:1",
    ]
    assert line_key(view.lines[0]) is None


def test_keep_selection_follows_the_session() -> None:
    infos = [_info(1, "a", Idle()), _info(2, "b", Idle())]
    view = _view(infos)
    assert keep_selection(f"session:{_id(2)}", view, 0) == 2
    assert keep_selection(f"session:{_id(1)}", view, 1) == 1


def test_keep_selection_falls_back_into_selectable_list() -> None:
    infos = [_info(1, "a", Running()), _info(2, "b", PermissionRequested(), group="beta")]
    key = f"session:{_id(1)}"
    collapsed = _view(infos, ViewState(collapsed=frozenset({"alpha"})))
    assert collapsed.lines[keep_selection(key, collapsed, 0)] == HeaderLine(
        group="alpha", text="alpha  1 live (collapsed)", collapsed=True
    )
    assert collapsed.lines[keep_selection(key, collapsed, 1)] == SessionLine(
        session_id=_id(2), text="  !b  permission  5m", attention=True
    )
    filtered = _view(infos, ViewState(attention_only=True))
    assert keep_selection(key, filtered, 0) == selectable(filtered)[0]
    assert keep_selection(key, filtered, 99) == selectable(filtered)[-1]
    assert keep_selection(None, filtered, -3) == selectable(filtered)[0]
    gone = _view(infos[1:])
    assert keep_selection(key, gone, 5) == selectable(gone)[-1]


def test_keep_selection_never_lands_on_an_expanded_header_or_info() -> None:
    view = _view([_info(1, "a", Running())], ViewState(collapsed=frozenset({"alpha"})))
    assert selectable(view) == (0,)  # R6: only the collapsed header can be selected
    assert keep_selection("session:x", view, 0) == 0
    empty = _view([])
    assert empty.lines == ()
    assert keep_selection(None, empty, 0) == -1


def test_details_lines_with_pending_permission() -> None:
    details = ClaudeDetails(
        model="opus",
        permission_mode="plan",
        last_tool="Bash",
        pending_permission="Bash(ls)",
        last_message="line one\nline two " + "x" * 300,
    )
    info = _info(1, "t", PermissionRequested(), details=details, metrics=_METRICS)
    lines = details_lines(info, now=_NOW, home=BOARD_HOME)
    assert lines[:6] == [
        "Folder: ~/git/x",
        "Model: opus",
        "Mode: plan",
        "Waiting for: Bash(ls)",
        "Last tool: Bash",
        "Last reply: line one line two " + "x" * 182,
    ]
    assert lines[6:] == ["Context: 42%", "Cost: $1.23", "Duration: 1h05"]


def test_details_lines_without_permission_or_metrics() -> None:
    info = _info(1, "t", Idle(), details=ClaudeDetails(model="opus"))
    assert details_lines(info, now=_NOW, home=BOARD_HOME) == ["Folder: ~/git/x", "Model: opus"]
    bare = _info(1, "t", Idle())
    assert details_lines(bare, now=_NOW, home=Path("/elsewhere")) == [
        f"Folder: {bare.row.session.cwd}"
    ]


def test_view_line_union_members() -> None:
    lines: tuple[ViewLine, ...] = (HeaderLine(group="g", text="t"), InfoLine("i"))
    assert SessionsView(lines=lines).lines == lines


def test_attention_filter_with_collapsed_groups() -> None:
    infos = [
        _info(1, "calm", Running(), group="a"),
        _info(2, "ask", PermissionRequested(), group="b"),
    ]
    state = ViewState(attention_only=True, collapsed=frozenset({"a", "b"}))
    view = _view(infos, state)
    assert [line.group for line in view.lines if isinstance(line, HeaderLine)] == ["b"]
    assert _texts(view) == ["b  1 live (collapsed)"]
    calm_only = _view(infos[:1], state)
    assert calm_only.lines == (InfoLine("Nothing needs your attention."),)


def test_collapsed_headers_are_selectable() -> None:
    infos = [_info(1, "a", Running(), group="a"), _info(2, "b", Idle(), group="b")]
    view = _view(infos, ViewState(collapsed=frozenset({"a", "b"})))
    assert [line_key(view.lines[i]) for i in selectable(view)] == ["group:a", "group:b"]
    open_view = _view(infos, ViewState(collapsed=frozenset({"b"})))
    assert line_key(open_view.lines[0]) is None
    assert [line_key(open_view.lines[i]) for i in selectable(open_view)][-1] == "group:b"


def test_collapsing_the_selected_group_selects_its_header() -> None:
    infos = [_info(1, "a", Running(), group="a"), _info(2, "b", Idle(), group="b")]
    view = _view(infos, ViewState(collapsed=frozenset({"b"})))
    index = keep_selection(f"session:{_id(2)}", view, 0, old_group="b")
    assert view.lines[index] == HeaderLine(group="b", text="b  1 live (collapsed)", collapsed=True)
    assert keep_selection("group:b", view, 0) == index
