"""Tests that kill the useful survivors of the mutation run of plan 4b.

Each test names the behaviour a mutant used to change: the roles of the spans (the core tests
look at the plain text, the TUI at the roles), time zones other than the machine's, and the
boundaries of the line fitting.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from meute.core.actor import Author, Channel
from meute.core.board_header import Tab, board_totals, tab_at, tabs_line, tasks_totals
from meute.core.board_sessions import board_sessions
from meute.core.board_view import (
    NO_SESSIONS,
    BoardData,
    RepoEntry,
    SessionEntry,
    SessionRow,
    confirm_delete_text,
    conflict_text,
    ended_notice,
    ended_text,
    launching_text,
)
from meute.core.claude_session import ClaudeDetails
from meute.core.errors import PromptNotPasted
from meute.core.instants import parse_zoned
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.quick_preview import (
    Displayed,
    preview_lines,
    quick_preview,
)
from meute.core.quota_view import QuotaLine, current_quota, quota_bar_lines
from meute.core.repo import Repo
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_details import details_card
from meute.core.session_project import session_project
from meute.core.session_state import Exited, Running, WaitingInput
from meute.core.sessions_view import InfoLine, SectionLine, ViewState, with_fold
from meute.core.sessions_view_text import (
    SessionInfo,
    attention_reason,
    card_first_line,
    card_more_lines,
    clip,
    dim_line,
    needs_you_first_line,
    ref_line,
    section_line,
)
from meute.core.status import Done, Priority
from meute.core.status_line import status_text
from meute.core.statusline import StatuslineData
from meute.core.styled import Role, Span, fit, plain
from meute.core.task import Note, TaskId
from meute.core.task_detail import task_detail_lines
from meute.core.task_line import due_short
from meute.core.task_postpone import Postpone, postpone
from meute.core.tasks_view import (
    EMPTY_TEXT,
    NO_PROJECT_TEXT,
    Grouping,
    TaskInfoLine,
    TaskScope,
    TasksState,
    build_tasks_view,
)
from support import BOARD_AT, NOW, at_due, board_data, make_task

HOME = Path("/home/me")
KATHMANDU = "Asia/Kathmandu"  # +05:45: no overlap with the zone of the machine or of `NOW`
REF = ProjectRef(id=ProjectId(1), name="meute")


def _roles(line: tuple[Span, ...]) -> list[tuple[str, Role]]:
    return [(span.text, span.role) for span in line]


# --- styled -----------------------------------------------------------------------------------


def test_fit_keeps_the_roles_of_the_cut_text() -> None:
    line = fit((Span("abcdef", Role.TITLE),), (Span("R", Role.OK),), 6)
    assert _roles(line) == [
        ("abc", Role.TITLE),
        ("…", Role.TITLE),
        (" ", Role.PLAIN),
        ("R", Role.OK),
    ]


def test_fit_with_a_right_part_that_leaves_one_column() -> None:
    # room == 1: one column for the left part, which is then cut to nothing but the ellipsis
    line = fit((Span("abc", Role.TITLE),), (Span("RR", Role.OK),), 4)
    assert plain(line) == "… RR"


def test_fit_pads_only_when_there_is_a_gap() -> None:
    assert fit((Span("ab"),), (), 2) == (Span("ab"),)
    assert fit((Span("ab"),), (), 3) == (Span("ab"), Span(" "))


def test_fit_cuts_a_line_to_a_zero_length_span_boundary() -> None:
    line = fit((Span("ab", Role.TITLE), Span("cd", Role.DIM)), (), 2)
    assert _roles(line) == [("ab", Role.TITLE)]


def test_fit_of_width_zero_is_empty() -> None:
    assert fit((Span("a"),), (), 0) == ()
    assert fit((Span("a"),), (), -1) == ()


# --- task_line / task_detail ------------------------------------------------------------------


def test_a_due_today_shows_its_clock_in_the_zone_of_now() -> None:
    now = parse_zoned(f"2026-10-14T10:30[{KATHMANDU}]")
    task = make_task(1, due=at_due(f"2026-10-14T18:00[{KATHMANDU}]"))
    assert due_short(task, now) == ("6pm", Role.DIM)


def test_a_done_task_with_a_due_has_no_short_due_in_its_detail() -> None:
    task = replace(make_task(1, due=at_due("2026-10-14T18:00[Europe/Paris]")), status=Done())
    status = task_detail_lines(
        task, notes=[], sessions=[], repo=None, now=NOW, home=None, width=80
    )[1]
    assert plain(status).endswith("due today 6pm")


def test_task_detail_roles() -> None:
    task = replace(
        make_task(12, due=at_due("2026-10-14T08:30[Europe/Paris]"), priority=Priority.URGENT),
        title="Review",
        project=REF,
    )
    repo = Repo(
        id=RepoId(1), path=HOME / "git" / "meute", name="meute", kind=None, discovered_at=NOW
    )
    note = Note(
        id=1,
        task_id=TaskId(12),
        body="CI",
        author=Author.USER,
        channel=Channel.TUI,
        session_id=None,
        created_at=datetime(2026, 10, 14, 8, 12, tzinfo=UTC),
    )
    session = Session(
        id=SessionId("11111111-1111-4111-8111-111111111111"),
        agent=AgentKind.BASH,
        title="plan",
        project_id=None,
        repo_id=None,
        task_id=TaskId(12),
        cwd=HOME,
        state=Exited(code=1),
        last_activity_at=NOW,
        created_at=NOW,
        ended_at=None,
    )
    other = replace(session, title="other", state=Running())
    lines = task_detail_lines(
        task, notes=[note], sessions=[session, other], repo=repo, now=NOW, home=HOME, width=100
    )
    assert _roles(lines[1]) == [
        ("Status   ", Role.DIM),
        ("todo", Role.PLAIN),
        (" · priority ", Role.DIM),
        ("urgent", Role.PLAIN),
        (" · due ", Role.DIM),
        ("today 8:30am", Role.PLAIN),
        (" (", Role.PLAIN),
        ("2h late", Role.LATE),
        (")", Role.PLAIN),
    ]
    assert _roles(lines[2]) == [
        ("Project  ", Role.DIM),
        ("meute", Role.KIND),
        (" · repo ~/git/meute", Role.DIM),
    ]
    assert _roles(lines[3]) == [("Notes    ", Role.DIM), ("10:12 ", Role.DIM), ("CI", Role.PLAIN)]
    assert _roles(lines[4]) == [
        ("Sessions ", Role.DIM),
        ("○ ", Role.IDLE),
        ("plan", Role.PLAIN),
        (" exited (1)", Role.DIM),
        (" · ", Role.DIM),
        ("● ", Role.RUNNING),
        ("other", Role.PLAIN),
        (" running", Role.DIM),
    ]


def test_a_floating_task_says_so_in_dim() -> None:
    line = task_detail_lines(
        make_task(1), notes=[], sessions=[], repo=None, now=NOW, home=None, width=80
    )[2]
    assert _roles(line) == [("Project  ", Role.DIM), ("floating", Role.DIM)]


def test_a_note_written_today_in_the_zone_of_now_shows_its_clock() -> None:
    now = parse_zoned(f"2026-10-14T10:30[{KATHMANDU}]")
    # 02:00 in Kathmandu on the 14th is still the 13th in Paris and in UTC
    created = parse_zoned(f"2026-10-14T02:00[{KATHMANDU}]")
    note = Note(
        id=1,
        task_id=TaskId(1),
        body="early",
        author=Author.USER,
        channel=Channel.TUI,
        session_id=None,
        created_at=created,
    )
    lines = task_detail_lines(
        make_task(1), notes=[note], sessions=[], repo=None, now=now, home=None, width=80
    )
    assert "Notes    02:00 early" in [plain(line) for line in lines]


# --- task_postpone ----------------------------------------------------------------------------


def test_next_monday_is_computed_in_the_zone_of_now() -> None:
    # Monday 12:00 in Kiritimati (+14) is still Sunday in Paris and in UTC.
    now = parse_zoned("2026-10-19T12:00[Pacific/Kiritimati]")
    due = postpone(Postpone.MONDAY, now)
    assert due == at_due("2026-10-26T09:00[Pacific/Kiritimati]")


# --- tasks_view -------------------------------------------------------------------------------


def test_the_information_lines_of_the_tasks_tab_are_dim() -> None:
    state = TasksState(scope=TaskScope.THIS_PROJECT)
    view = build_tasks_view([make_task(1)], state, now=NOW, project=None, width=60)
    assert view.lines == (TaskInfoLine((Span(NO_PROJECT_TEXT, Role.DIM),)),)
    empty = build_tasks_view([], TasksState(), now=NOW, project=None, width=60)
    assert empty.lines == (TaskInfoLine((Span(EMPTY_TEXT, Role.DIM),)),)


def test_project_groups_keep_going_after_a_task_that_is_not_listed() -> None:
    old = replace(
        make_task(1, status=Done(), completed_at=NOW - timedelta(days=3)),
        project=REF,
    )
    open_ = replace(make_task(2), project=REF)
    state = TasksState(grouping=Grouping.PROJECT, collapsed=frozenset())
    view = build_tasks_view([old, open_], state, now=NOW, project=None, width=60)
    assert [plain(line.spans).rstrip() for line in view.lines] == [
        "▼ meute (1)",
        "  ·    task 2  @meute",
    ]


# --- quick_preview ----------------------------------------------------------------------------


def test_an_empty_entry_still_shows_the_default_project() -> None:
    for text in ("", "   "):
        preview = quick_preview(text, now=NOW, default=REF, projects=[REF])
        assert preview.project == Displayed(REF)


def test_a_title_less_entry_keeps_the_default_project_and_the_error() -> None:
    preview = quick_preview("@meute", now=NOW, default=REF, projects=[REF])
    assert preview.project == Displayed(REF)
    assert preview.error == "empty title"


def test_preview_roles() -> None:
    projects = [REF]
    named = quick_preview("t @meute !! >tomorrow", now=NOW, default=None, projects=projects)
    lines = preview_lines(named, NOW)
    assert _roles(lines[1]) == [("Project   ", Role.DIM), ("meute", Role.KIND)]
    assert _roles(lines[-1]) == [("Enter create · Esc cancel", Role.DIM)]
    shown = preview_lines(quick_preview("t", now=NOW, default=REF, projects=projects), NOW)
    assert _roles(shown[1]) == [
        ("Project   ", Role.DIM),
        ("meute", Role.KIND),
        ("  (displayed session · @none: floating)", Role.DIM),
    ]
    floating = preview_lines(quick_preview("t", now=NOW, default=None, projects=projects), NOW)
    assert _roles(floating[1]) == [
        ("Project   ", Role.DIM),
        ("floating", Role.KIND),
        ("  (no displayed session)", Role.DIM),
    ]
    none = preview_lines(quick_preview("t @none", now=NOW, default=None, projects=projects), NOW)
    assert _roles(none[1]) == [("Project   ", Role.DIM), ("floating", Role.KIND)]
    unknown = preview_lines(quick_preview("t @zzz", now=NOW, default=None, projects=projects), NOW)
    assert _roles(unknown[-1]) == [
        ("Cannot create: fix the project or use @none · Esc cancel", Role.HIGH)
    ]
    empty = preview_lines(quick_preview("", now=NOW, default=None, projects=projects), NOW)
    assert _roles(empty[-1]) == [("Cannot create: empty title · Esc cancel", Role.HIGH)]


# --- board_header -----------------------------------------------------------------------------


def _board(**kwargs: object) -> BoardData:
    return BoardData(repos=(), orphans=(), home=HOME, **kwargs)  # pyright: ignore[reportArgumentType] — test helper


def _session(title: str, state: Running | Exited | WaitingInput, *, minutes: int = 0) -> Session:
    return Session(
        id=SessionId(f"{len(title):08d}-1111-4111-8111-111111111111"),
        agent=AgentKind.CLAUDE,
        title=title,
        project_id=None,
        repo_id=None,
        task_id=None,
        cwd=HOME / "git" / title,
        state=state,
        last_activity_at=BOARD_AT - timedelta(minutes=minutes),
        created_at=BOARD_AT,
        ended_at=None,
    )


def test_the_tab_under_a_column() -> None:
    line = tabs_line(Tab.SESSIONS, overdue=0, totals="", width=30)
    assert tab_at(line, 0) is Tab.SESSIONS
    assert tab_at(line, 9) is Tab.SESSIONS  # " Sessions " covers columns 0..9
    assert tab_at(line, 10) is Tab.TASKS
    assert tab_at(line, 16) is Tab.TASKS  # " Tasks " covers columns 10..16
    assert tab_at(line, 17) is None
    assert tab_at(line, 29) is None


def test_the_overdue_count_appears_from_one() -> None:
    assert "1!" in plain(tabs_line(Tab.TASKS, overdue=1, totals="", width=30))
    assert "!" not in plain(tabs_line(Tab.TASKS, overdue=0, totals="", width=30))
    assert tasks_totals(3, 1) == "3 open · 1 overdue"
    assert tasks_totals(3, 0) == "3 open"


def test_board_totals_sum_what_the_sessions_reported() -> None:
    first = _session("a", Running())
    second = _session("bb", WaitingInput())
    ended = _session("ccc", Exited(code=0))
    silent = _session("dddd", Running())
    data = _board(
        sessions=tuple(
            SessionRow(session=s, has_pane=True, displayed=False)
            for s in (first, second, ended, silent)
        ),
        metrics={
            first.id: StatuslineData(duration_ms=3_600_000, cost_usd=1.25),
            second.id: StatuslineData(duration_ms=600_000, cost_usd=0.5),
            ended.id: StatuslineData(duration_ms=60_000, cost_usd=None),
        },
    )
    assert board_totals(data) == "3 live · 1h11 · $1.75"
    bare = _board(sessions=(SessionRow(session=first, has_pane=True, displayed=False),))
    assert board_totals(bare) == "1 live"
    only_cost = _board(sessions=data.sessions, metrics={first.id: StatuslineData(cost_usd=2.0)})
    assert board_totals(only_cost) == "3 live · $2.00"
    only_time = _board(
        sessions=data.sessions, metrics={first.id: StatuslineData(duration_ms=60_000)}
    )
    assert board_totals(only_time) == "3 live · 1m"


# --- sessions_view_text -----------------------------------------------------------------------


def _info(  # noqa: PLR0913 — a test builder with one keyword per field
    title: str = "build",
    state: Running | Exited | WaitingInput | None = None,
    *,
    displayed: bool = False,
    details: ClaudeDetails | None = None,
    metrics: StatuslineData | None = None,
    minutes: int = 5,
) -> SessionInfo:
    session = _session(title, Running() if state is None else state, minutes=minutes)
    return SessionInfo(
        row=SessionRow(session=session, has_pane=True, displayed=displayed),
        details=details,
        metrics=metrics,
        group="meute",
    )


def test_card_first_line_roles() -> None:
    line = card_first_line(_info(), now=BOARD_AT, width=60)
    assert _roles(line) == [
        ("  ● ", Role.RUNNING),
        ("build", Role.TITLE),
        ("  ", Role.PLAIN),
        ("running", Role.RUNNING),
        ("  5m ago", Role.DIM),
    ]
    assert line[0] == Span("  ● ", Role.RUNNING)
    assert line[-1] == Span("  5m ago", Role.DIM)
    shown = card_first_line(_info(displayed=True), now=BOARD_AT, width=60)
    assert shown[:2] == (Span("▶", Role.ACCENT), Span(" ● ", Role.RUNNING))


def test_needs_you_and_reference_lines() -> None:
    waiting = _info(state=WaitingInput())
    line = needs_you_first_line(waiting, width=70)
    assert line[0] == Span("  ! ", Role.ATTENTION)
    assert line[1].role is Role.TITLE
    assert line[-2:] == (
        Span(" · meute · ", Role.DIM),
        Span("waiting for your reply", Role.ATTENTION),
    )
    ref = ref_line(waiting, width=70)
    assert ref[0] == Span("  ! ", Role.ATTENTION)
    assert ref[1].role is Role.DIM
    assert ref[-1] == Span("  ↑ needs you", Role.DIM)
    marked = needs_you_first_line(
        replace(waiting, row=replace(waiting.row, displayed=True)), width=70
    )
    assert marked[:2] == (Span("▶", Role.ACCENT), Span(" ! ", Role.ATTENTION))


def test_the_title_keeps_one_column_when_only_one_is_left() -> None:
    # head "  ! " (4) and tail "  ↑ needs you" (13): a width of 18 leaves exactly one column
    line = ref_line(_info(title="abcdef", state=WaitingInput()), width=18)
    assert plain(line) == "  ! …  ↑ needs you"
    # no column left: the title is cut with the rest of the line
    cut = ref_line(_info(title="abcdef", state=WaitingInput()), width=17)
    assert len(plain(cut)) == 17
    assert plain(cut).endswith("…")


def test_clip_keeps_a_single_column() -> None:
    assert plain(clip((Span("abc"),), 1)) == "…"
    assert plain(clip((Span("abc"),), 2)) == "a…"
    assert clip((Span("abc"),), 0) == ()


def test_card_more_lines_roles() -> None:
    info = _info(
        details=ClaudeDetails(model="opus", permission_mode="auto", last_tool="Bash"),
        metrics=StatuslineData(
            duration_ms=4_740_000, cost_usd=4.4, context_pct=62, worktree_branch="feat/x"
        ),
    )
    first, second = card_more_lines(info, width=80)
    assert _roles(first) == [
        ("    ", Role.DIM),
        ("1h19", Role.DIM),
        (" · ", Role.DIM),
        ("$4.40", Role.DIM),
        (" · ", Role.DIM),
        ("62%", Role.WARN),
        (" · ", Role.DIM),
        ("opus", Role.DIM),
        (" · ", Role.DIM),
        ("auto", Role.RISKY),
    ]
    assert _roles(second) == [
        ("    └ ", Role.DIM),
        ("feat/x", Role.DIM),
        (" · ", Role.DIM),
        ("Bash", Role.DIM),
    ]


def test_sections_and_information_lines_are_dim() -> None:
    assert section_line("Without session", 3, folded=False) == (
        Span("▼ Without session (3)", Role.DIM),
    )
    assert section_line("Ended", 1, folded=True) == (Span("▶ Ended (1)", Role.DIM),)
    assert dim_line("nothing", 20) == (Span("nothing", Role.DIM),)


def test_a_session_card_is_a_one_line_title() -> None:
    assert plain(details_card(_info(), home=HOME, width=40)[0]).startswith("─ build ")


def test_details_card_roles() -> None:
    info = _info(details=ClaudeDetails(last_message="Done.", pending_permission="Bash ls"))
    rule, reply, folder, waiting = details_card(info, home=HOME, width=40)
    assert plain(rule) == "─ build " + "─" * 32
    assert rule[0].role is Role.ACCENT
    assert _roles(reply) == [("Reply       ", Role.DIM), ("Done.", Role.PLAIN)]
    assert _roles(folder) == [("Folder      ", Role.DIM), ("~/git/build", Role.PLAIN)]
    assert _roles(waiting) == [("Waiting for ", Role.DIM), ("Bash ls", Role.PLAIN)]
    # the rule is cut when the title is longer than the width, and is never padded past it
    long_rule = details_card(
        replace(info, row=replace(info.row, session=replace(info.row.session, title="t" * 50))),
        home=HOME,
        width=20,
    )[0]
    assert len(plain(long_rule)) == 20
    assert plain(long_rule).endswith("…")
    exact = details_card(_info(title="x" * 5), home=HOME, width=len("─ xxxxx "))[0]
    assert plain(exact) == "─ xxxxx "


def test_every_state_has_an_attention_reason() -> None:
    assert attention_reason(_info(state=Running())) == "running"
    assert attention_reason(_info(state=Exited(code=1))) == "exited (1)"
    assert attention_reason(_info(state=WaitingInput())) == "waiting for your reply"


def test_a_title_cut_with_its_line_keeps_its_role() -> None:
    cut = ref_line(_info(title="abcdef", state=WaitingInput()), width=17)
    assert any(span.text.startswith("abc") and span.role is Role.DIM for span in cut)


# --- board_view texts, errors, session project, folding ---------------------------------------


def test_task_texts_of_the_footer_name_the_task_and_neutralise_the_title() -> None:
    assert confirm_delete_text(TaskId(12), "Fix\x1b[31m it") == (
        'Delete #12 "Fix\ufffd[31m it"? y: yes · any other key: no'
    )
    assert conflict_text(TaskId(12)) == "#12 was modified in the meantime: reloaded"
    assert launching_text(TaskId(12)) == "Launching Claude on #12…"
    assert ended_text("a\x1bb") == '"a\ufffdb" has ended: c starts a new Claude session here'


def test_prompt_not_pasted_keeps_its_task_and_message() -> None:
    error = PromptNotPasted(TaskId(12))
    assert str(error) == "#12: prompt not pasted (Claude not ready after 10 s)"
    assert error.task_id == 12


def test_ended_notice_only_for_an_ended_session_without_a_pane() -> None:
    ended = _session("done", Exited(code=0))
    live = _session("live", Running())
    assert ended_notice(
        SessionEntry(row=SessionRow(session=ended, has_pane=False, displayed=False))
    ) == ended_text("done")
    assert (
        ended_notice(SessionEntry(row=SessionRow(session=ended, has_pane=True, displayed=False)))
        is None
    )
    assert (
        ended_notice(SessionEntry(row=SessionRow(session=live, has_pane=False, displayed=False)))
        is None
    )
    repo = Repo(id=RepoId(1), path=HOME / "git" / "r", name="r", kind=None, discovered_at=NOW)
    assert ended_notice(RepoEntry(repo=repo)) is None


def test_session_project_is_the_own_project_else_the_repository_name() -> None:
    other = ProjectRef(id=ProjectId(2), name="Other")
    repo = Repo(
        id=RepoId(1), path=HOME / "git" / "meute", name="Meute", kind=None, discovered_at=NOW
    )
    base = _session("s", Running())
    assert session_project(base, projects=[REF, other], repos={}) is None
    assert session_project(base, projects=[REF, other], repos={repo.id: repo}) is None
    with_repo = replace(base, repo_id=repo.id)
    assert session_project(with_repo, projects=[REF, other], repos={repo.id: repo}) == REF
    own = replace(base, project_id=other.id)
    assert session_project(own, projects=[REF, other], repos={}) == other


def test_folding_a_group_forgets_that_it_was_expanded() -> None:
    state = ViewState(expanded=frozenset({"g"}))
    folded = with_fold(state, "g", fold=True)
    assert "g" in folded.collapsed
    assert "g" not in folded.expanded
    shown = with_fold(folded, "g", fold=False)
    assert "g" in shown.expanded
    assert "g" not in shown.collapsed


def test_the_status_line_says_overdue_from_one() -> None:
    assert status_text(None, 0, None, 1) == "1 overdue"
    assert status_text(None, 0, None, 0) == ""


def test_sections_are_keyed_by_their_title() -> None:
    board = board_sessions(board_data(), ViewState())
    sections = [line.section for line in board.view.lines if isinstance(line, SectionLine)]
    assert sections
    assert all(isinstance(section, str) and section for section in sections)


def test_the_hint_without_sessions_is_followed_by_a_blank_line_and_the_rest() -> None:
    data = replace(board_data(), sessions=(), ended=(), orphans=())
    board = board_sessions(data, ViewState())
    assert board.view.lines[0] == InfoLine(spans=(Span(NO_SESSIONS),))
    assert board.view.lines[1] == InfoLine(spans=())
    bare = board_sessions(replace(data, repos=()), ViewState())
    assert bare.view.lines == (InfoLine(spans=(Span(NO_SESSIONS),)),)


def test_board_sessions_default_width_is_the_board_width() -> None:
    long = SessionRow(session=_session("t" * 100, Running()), has_pane=True, displayed=False)
    data = replace(board_data(), sessions=(long,), now=BOARD_AT)
    lines = board_sessions(data, ViewState()).view.lines
    assert max(len(line.text) for line in lines) == 72


# --- quota bars -------------------------------------------------------------------------------


def test_quota_bars_show_every_time_in_the_given_zone() -> None:
    zone = ZoneInfo(KATHMANDU)
    line = QuotaLine(
        five_hour_pct=42,
        five_hour_resets_at=datetime(2026, 10, 14, 12, 0, tzinfo=UTC),
        seven_day_pct=10,
        seven_day_resets_at=datetime(2026, 10, 14, 12, 0, tzinfo=UTC),
        limit_at=datetime(2026, 10, 14, 11, 0, tzinfo=UTC),
        peak="",
    )
    five, seven = quota_bar_lines(line, local=zone)
    assert plain(five) == "5h ████░░░░░░ 42%  resets 17:45 · limit ~16:45"
    assert plain(seven) == "7d █░░░░░░░░░ 10%  resets Wed 17:45"
    assert five[2] == Span("  resets 17:45", Role.DIM)
    assert seven[2] == Span("  resets Wed 17:45", Role.DIM)


def test_a_window_that_resets_exactly_now_is_over() -> None:
    sample = StatuslineData(
        five_hour_pct=5,
        five_hour_resets_at=NOW,
        seven_day_pct=7,
        seven_day_resets_at=NOW,
    )
    assert current_quota(sample, now=NOW) == StatuslineData()
