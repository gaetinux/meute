"""Tests of the Sessions view's cards, the "Needs you" section and the project blocks."""

from dataclasses import replace
from datetime import timedelta

from hypothesis import given
from hypothesis import strategies as st

from meute.core.agents import AgentInfo
from meute.core.board_sessions import board_sessions, line_info
from meute.core.board_view import BoardData, SessionRow
from meute.core.claude_session import ClaudeDetails
from meute.core.project import RepoId
from meute.core.repo import Repo
from meute.core.session import SessionId
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
    REPOS_FOLDED_ABOVE,
    CardLine,
    HeaderLine,
    InfoLine,
    RefLine,
    RepoLine,
    SectionLine,
    SessionInfo,
    SessionLine,
    SessionsView,
    ViewState,
    attention_reason,
    build_view,
    keep_selection,
    line_key,
    selectable,
    session_index,
    with_fold,
)
from meute.core.statusline import StatuslineData
from meute.core.styled import Role, Span
from support import BOARD_AT, BOARD_HOME, board_repo, board_session

_NOW = BOARD_AT + timedelta(hours=2)
_WIDTH = 72


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
        width=_WIDTH,
    )


def _texts(view: SessionsView) -> list[str]:
    return [line.text for line in view.lines]


_FULL_METRICS = StatuslineData(
    context_pct=42.0, cost_usd=1.234, duration_ms=3_900_000, worktree_branch="feat/x"
)
_FULL_DETAILS = ClaudeDetails(model="opus", permission_mode="auto", last_tool="Bash")


def test_full_card_has_three_lines_and_its_block_header() -> None:
    info = _info(
        1, "build", Running(), metrics=_FULL_METRICS, details=_FULL_DETAILS, repo_id=RepoId(1)
    )
    view = _view([info], repos=[board_repo(1, "alpha", "python")])
    left = "▼ alpha ◆ python · 1 live · $1.23"
    assert _texts(view) == [
        left + " " * (_WIDTH - len(left) - len("+ session")) + "+ session",
        "  ● build  running  5m ago",
        "    1h05 · $1.23 · 42% · opus · auto",
        "    └ feat/x · Bash",
    ]
    header, first, second, third = view.lines
    assert header == HeaderLine(group="alpha", spans=header.spans, repo_id=RepoId(1))
    assert header.spans[:3] == (
        Span("▼ alpha", Role.TITLE),
        Span(" ◆ python", Role.KIND),
        Span(" · 1 live · $1.23", Role.DIM),
    )
    assert header.spans[-1] == Span("+ session", Role.RUNNING)
    assert isinstance(first, SessionLine)
    assert first.spans[:2] == (Span("  ● ", Role.RUNNING), Span("build", Role.TITLE))
    assert Span("running", Role.RUNNING) in first.spans
    assert isinstance(second, CardLine)
    assert second.session_id == _id(1)
    assert Span("42%", Role.OK) in second.spans
    assert Span("auto", Role.RISKY) in second.spans
    assert isinstance(third, CardLine)
    assert not any(line.band for line in view.lines)


def test_context_takes_its_level_and_safe_modes_stay_dim() -> None:
    metrics = StatuslineData(context_pct=85.0)
    info = _info(1, "t", Running(), metrics=metrics, details=ClaudeDetails(permission_mode="plan"))
    second = _view([info]).lines[2]
    assert second.text == "    85% · plan"
    assert Span("85%", Role.HIGH) in second.spans
    assert Span("plan", Role.DIM) in second.spans
    warn = _info(1, "t", Running(), metrics=StatuslineData(context_pct=50.0))
    assert Span("50%", Role.WARN) in _view([warn]).lines[2].spans


def test_half_known_cards_leave_out_unknown_lines() -> None:
    bare = _info(1, "t", Idle())
    assert _texts(_view([bare]))[1:] == ["  ○ t  idle  5m ago"]
    branch_only = _info(1, "t", Running(), metrics=StatuslineData(worktree_branch="main"))
    assert _texts(_view([branch_only]))[1:] == ["  ● t  running  5m ago", "    └ main"]
    tool_only = _info(
        1, "t", Running(), age=timedelta(seconds=10), details=ClaudeDetails(last_tool="Read")
    )
    assert _texts(_view([tool_only]))[1:] == ["  ● t  running  now", "    └ Read"]
    cost_only = _info(1, "t", Running(), metrics=StatuslineData(cost_usd=4.4))
    assert _texts(_view([cost_only]))[1:] == ["  ● t  running  5m ago", "    $4.40"]


def test_header_without_repository_has_no_kind_nor_session_button() -> None:
    view = _view([_info(1, "a", Running()), _info(2, "b", Exited(code=0))])
    header = view.lines[0]
    assert header == HeaderLine(group="alpha", spans=header.spans, repo_id=None)
    assert header.text == "▼ alpha · 1 live"


def test_collapsed_header_drops_the_session_button() -> None:
    info = _info(1, "a", Running(), repo_id=RepoId(1), metrics=StatuslineData(cost_usd=2.0))
    view = _view(
        [info], ViewState(collapsed=frozenset({"alpha"})), repos=[board_repo(1, "alpha", "go")]
    )
    assert _texts(view) == ["▶ alpha ◆ go · 1 live · $2.00"]
    assert view.lines[0] == HeaderLine(
        group="alpha", spans=view.lines[0].spans, collapsed=True, repo_id=RepoId(1)
    )


def test_attention_reason() -> None:
    asking = ClaudeDetails(pending_permission="Bash(rm -rf build)")
    assert (
        attention_reason(_info(1, "t", PermissionRequested(), details=asking))
        == "permission: Bash(rm -rf build)"
    )
    assert attention_reason(_info(1, "t", PermissionRequested())) == "permission requested"
    assert attention_reason(_info(1, "t", WaitingInput())) == "waiting for your reply"
    assert attention_reason(_info(1, "t", MaybeStuck())) == "stuck?"


def test_session_needing_attention_moves_to_needs_you() -> None:
    asking = _info(
        2,
        "ask",
        PermissionRequested(),
        group="beta",
        details=ClaudeDetails(pending_permission="Bash(ls)", last_tool="Bash"),
    )
    calm = _info(1, "calm", Running(), group="beta")
    view = _view([calm, asking])
    assert _texts(view) == [
        "Needs you (1)",
        "  ! ask · beta · permission: Bash(ls)",
        "    └ Bash",
        "",
        "▼ beta · 2 live",
        "  ● calm  running  5m ago",
        "  ! ask  ↑ needs you",
    ]
    section = view.lines[0]
    assert section == SectionLine(
        section="Needs you", spans=(Span("Needs you (1)", Role.ATTENTION),), collapsed=False
    )
    assert [line.band for line in view.lines[1:3]] == [True, True]
    assert not any(line.band for line in view.lines[3:])
    ref = view.lines[-1]
    assert ref == RefLine(session_id=_id(2), spans=ref.spans)
    assert ref.spans[0] == Span("  ! ", Role.ATTENTION)
    first = view.lines[1]
    assert first == SessionLine(session_id=_id(2), spans=first.spans, attention=True, band=True)
    assert Span("permission: Bash(ls)", Role.ATTENTION) in first.spans
    keys = [line_key(view.lines[i]) for i in selectable(view)]
    assert keys.count(f"session:{_id(2)}") == 1
    assert session_index(view, _id(2)) == 1
    assert session_index(view, _id(9)) == -1


def test_needs_you_lists_every_waiting_session_in_group_order() -> None:
    infos = [
        _info(1, "w", WaitingInput(), group="zeta"),
        _info(2, "s", MaybeStuck(), group="alpha"),
    ]
    texts = _texts(_view(infos))
    assert texts[:3] == [
        "Needs you (2)",
        "  ! s · alpha · stuck?",
        "  ! w · zeta · waiting for your reply",
    ]


def test_attention_filter_keeps_its_behaviour() -> None:
    infos = [
        _info(1, "calm", Running(), group="a"),
        _info(2, "ask", PermissionRequested(), group="b"),
    ]
    view = _view(infos, ViewState(attention_only=True))
    assert _texts(view) == ["▼ b · 1 live", "  ! ask  permission  5m ago"]
    assert not any(isinstance(line, (SectionLine, RefLine)) or line.band for line in view.lines)
    calm_only = _view(infos[:1], ViewState(attention_only=True))
    assert _texts(calm_only) == ["Nothing needs your attention."]


def _repos(count: int) -> list[Repo]:
    return [board_repo(n, f"r{n}", None) for n in range(1, count + 1)]


def test_without_session_folded_above_five_repositories() -> None:
    assert REPOS_FOLDED_ABOVE == 5
    five = _view([], repos=_repos(5))
    assert _texts(five) == ["▼ Without session (5)", *(f"  r{n}" for n in range(1, 6))]
    assert [type(line) for line in five.lines[1:]] == [RepoLine] * 5
    six = _view([], repos=_repos(6))
    assert _texts(six) == ["▶ Without session (6)"]
    assert line_key(six.lines[0]) is not None
    assert line_key(five.lines[0]) is None


def test_without_session_folds_and_unfolds_against_its_default() -> None:
    six = _view([], repos=_repos(6))
    key = six.lines[0]
    assert isinstance(key, SectionLine)
    opened = with_fold(ViewState(), "section:Without session", fold=False)
    assert len(_view([], opened, repos=_repos(6)).lines) == 7
    closed = with_fold(opened, "section:Without session", fold=True)
    assert _texts(_view([], closed, repos=_repos(5))) == ["▶ Without session (5)"]


def test_bottom_blocks_are_separated_by_a_blank_line() -> None:
    repos = [board_repo(1, "meute", "rust"), board_repo(2, "notes", None)]
    infos = [
        _info(1, "live", Idle(), repo_id=RepoId(1)),
        _info(2, "dead", Exited(code=1), repo_id=RepoId(1)),
    ]
    outside = [
        AgentInfo(pid=4, cwd="/home/me/w", kind="cli", session_id="s", name="ext", status="busy")
    ]
    view = _view(infos, repos=repos, outside=outside, orphans=["%7"])
    assert _texts(view)[1:] == [
        "  ○ live  idle  5m ago",
        "  + 1 ended (e to show)",
        "─" * _WIDTH,
        "▼ Without session (1)",
        "  notes",
        "▼ Outside meute (1)",
        "  ext  busy  ~/w",
        "▼ Orphans (1)",
        "  %7",
    ]
    folded = ViewState(collapsed=frozenset({"section:Outside meute", "section:Orphans"}))
    assert _texts(_view(infos, folded, outside=outside, orphans=["%7"]))[-3:] == [
        "─" * _WIDTH,
        "▶ Outside meute (1)",
        "▶ Orphans (1)",
    ]


def test_hostile_long_title_fits_the_width() -> None:
    title = "\x1b[2J" + "x" * 300
    infos = [
        _info(1, title, Running(), group="g\x1b[31m" + "y" * 200),
        _info(2, title, PermissionRequested(), details=ClaudeDetails(pending_permission="p" * 300)),
    ]
    view = _view(infos)
    for line in view.lines:
        assert len(line.text) <= _WIDTH
        assert "\x1b" not in line.text
    sessions = [line for line in view.lines if isinstance(line, SessionLine)]
    assert [len(line.text) for line in sessions] == [_WIDTH, _WIDTH]
    running = next(line for line in sessions if not line.attention)
    assert running.text.endswith("…  running  5m ago")


def test_card_and_ref_lines_lead_to_their_session() -> None:
    asking = replace(
        board_session(_id(1), "ask", BOARD_HOME, None, exited=False), state=PermissionRequested()
    )
    calm = board_session(_id(2), "calm", BOARD_HOME, None, exited=False)
    data = BoardData(
        sessions=(
            SessionRow(session=asking, has_pane=True, displayed=False),
            SessionRow(session=calm, has_pane=True, displayed=False),
        ),
        repos=(),
        orphans=(),
        home=BOARD_HOME,
        metrics={_id(2): StatuslineData(worktree_branch="main")},
        now=BOARD_AT,
    )
    model = board_sessions(data, ViewState(), width=60)
    for index, line in enumerate(model.view.lines):
        info = line_info(model, index)
        match line:
            case CardLine() | RefLine() | SessionLine():
                assert info is not None
                assert info.row.session.id == line.session_id
            case _:
                assert info is None
    assert any(isinstance(line, RefLine) for line in model.view.lines)
    assert any(isinstance(line, CardLine) for line in model.view.lines)
    assert all(len(line.text) <= 60 for line in model.view.lines)


_STATES: list[SessionState] = [
    Running(),
    Idle(),
    PermissionRequested(),
    WaitingInput(),
    MaybeStuck(),
    Exited(code=0),
]
_KEYS = ["a", "b", "section:Needs you", "section:Without session"]


@given(
    picks=st.lists(
        st.tuples(st.sampled_from(_STATES), st.sampled_from(["a", "b"]), st.booleans()),
        max_size=8,
    ),
    folds=st.lists(st.tuples(st.sampled_from(_KEYS), st.booleans()), max_size=6),
    repos=st.integers(min_value=0, max_value=8),
    attention_only=st.booleans(),
    show_ended=st.booleans(),
    old=st.integers(min_value=0, max_value=10),
    fallback=st.integers(min_value=-3, max_value=20),
)
def test_selection_never_rests_on_a_card_or_ref_line(  # noqa: PLR0913 — hypothesis draws
    *,
    picks: list[tuple[SessionState, str, bool]],
    folds: list[tuple[str, bool]],
    repos: int,
    attention_only: bool,
    show_ended: bool,
    old: int,
    fallback: int,
) -> None:
    infos = [
        _info(
            n, f"s{n}", state, group=group, details=ClaudeDetails(last_tool="x") if rich else None
        )
        for n, (state, group, rich) in enumerate(picks, start=1)
    ]
    state = ViewState(attention_only=attention_only, show_ended=show_ended)
    before = _view(infos, state, repos=_repos(repos))
    for key, fold in folds:
        state = with_fold(state, key, fold=fold)
    view = _view(infos, state, repos=_repos(repos))
    for index in selectable(view):
        assert not isinstance(view.lines[index], (CardLine, RefLine, InfoLine))
    old_key = line_key(before.lines[old]) if old < len(before.lines) else f"session:{_id(old)}"
    chosen = keep_selection(old_key, view, fallback)
    assert chosen == -1 or chosen in selectable(view)
    if chosen != -1:
        assert not isinstance(view.lines[chosen], (CardLine, RefLine))
