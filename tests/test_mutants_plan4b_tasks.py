"""Tests that kill the useful survivors of the mutation run of plan 4b: line fitting and tasks.

Each test names the behaviour a mutant used to change: the roles of the spans (the core tests
look at the plain text, the TUI at the roles), time zones other than the machine's, and the
boundaries of the line fitting.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from meute.core.actor import Author, Channel
from meute.core.instants import parse_zoned
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.quick_preview import (
    Displayed,
    preview_lines,
    quick_preview,
)
from meute.core.repo import Repo
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import Exited, Running
from meute.core.status import Done, Priority
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
from support import NOW, at_due, make_task

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
