"""Tests of the detail lines of a task in the Tasks tab."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from meute.core.actor import Author, Channel
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.repo import Repo
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import Exited, Running, WaitingInput
from meute.core.status import Blocked, Priority
from meute.core.styled import Role, plain
from meute.core.task import Note, TaskId
from meute.core.task_detail import task_detail_lines
from support import NOW, at_due, make_task

HOME = Path("/home/me")
REPO = Repo(
    id=RepoId(1),
    path=HOME / "git" / "meute",
    name="meute",
    kind=None,
    discovered_at=datetime(2026, 10, 1, tzinfo=UTC),
)


def _note(note_id: int, body: str, created: datetime) -> Note:
    return Note(
        id=note_id,
        task_id=TaskId(12),
        body=body,
        author=Author.USER,
        channel=Channel.TUI,
        session_id=None,
        created_at=created,
    )


def _session(title: str, state: Running | Exited | WaitingInput) -> Session:
    return Session(
        id=SessionId("11111111-1111-4111-8111-111111111111"),
        agent=AgentKind.BASH,
        title=title,
        project_id=None,
        repo_id=None,
        task_id=TaskId(12),
        cwd=HOME,
        state=state,
        last_activity_at=NOW,
        created_at=NOW,
        ended_at=None,
    )


def _full():  # noqa: ANN202 — a test helper
    task = replace(
        make_task(12, due=at_due("2026-10-14T08:30[Europe/Paris]"), priority=Priority.URGENT),
        title="Review PR #11",
        description="\n  Check the tabs\nand the quick add.\n",
        project=ProjectRef(id=ProjectId(1), name="meute"),
    )
    notes = [
        _note(1, "oldest", datetime(2026, 10, 14, 6, 0, tzinfo=UTC)),
        _note(2, "CI is green", datetime(2026, 10, 14, 8, 12, tzinfo=UTC)),
        _note(3, "snapshots read", datetime(2026, 10, 12, 7, 40, tzinfo=UTC)),
    ]
    sessions = [_session("plan-4b", Running()), _session("review-11", Exited(code=1))]
    return task_detail_lines(
        task, notes=notes, sessions=sessions, repo=REPO, now=NOW, home=HOME, width=60
    )


def test_full(snapshot: SnapshotAssertion) -> None:
    assert [plain(line) for line in _full()] == snapshot


def test_minimal(snapshot: SnapshotAssertion) -> None:
    lines = task_detail_lines(
        make_task(3), notes=[], sessions=[], repo=None, now=NOW, home=None, width=40
    )
    assert [plain(line) for line in lines] == snapshot


def test_lines_fit_the_width() -> None:
    for width in (10, 30, 60):
        lines = task_detail_lines(
            replace(make_task(12), title="t" * 80, description="d" * 80),
            notes=[_note(1, "n" * 80, NOW)],
            sessions=[_session("s" * 80, Running())],
            repo=REPO,
            now=NOW,
            home=HOME,
            width=width,
        )
        assert all(len(plain(line)) <= width for line in lines)
    assert len(plain(lines[0])) == width


def test_old_note_shows_its_day() -> None:
    old = _note(1, "older", datetime(2026, 10, 5, 7, 40, tzinfo=UTC))
    lines = task_detail_lines(
        make_task(1), notes=[old], sessions=[], repo=None, now=NOW, home=None, width=80
    )
    assert "Notes    Oct 05 older" in [plain(line) for line in lines]


def test_roles() -> None:
    lines = _full()
    assert lines[0][0].role is Role.ACCENT
    status = {span.text: span.role for span in lines[1]}
    assert status["2h late"] is Role.LATE
    assert any(s.text == "● " and s.role is Role.RUNNING for s in lines[-1])
    assert any(s.text == "○ " and s.role is Role.IDLE for s in lines[-1])


def test_blocked_reason_is_not_repeated() -> None:
    task = replace(make_task(1), status=Blocked(reason="waiting for CI"))
    line = task_detail_lines(task, notes=[], sessions=[], repo=None, now=NOW, home=None, width=80)[
        1
    ]
    assert plain(line).count("waiting for CI") == 1


def test_attention_symbol() -> None:
    lines = task_detail_lines(
        make_task(1),
        notes=[],
        sessions=[_session("ask", WaitingInput())],
        repo=None,
        now=NOW,
        home=None,
        width=80,
    )
    assert plain(lines[-1]) == "Sessions ! ask waiting for your reply"


def test_unsafe_text_is_neutralised() -> None:
    task = replace(make_task(1), title="a\x1b[2Jb", description="x\x1b]0;y\x07")
    lines = task_detail_lines(task, notes=[], sessions=[], repo=None, now=NOW, home=None, width=80)
    assert all("\x1b" not in plain(line) and "\x07" not in plain(line) for line in lines)


def test_unsafe_repository_path_is_neutralised() -> None:
    repo = replace(REPO, path=HOME / "git" / "a\x1b]0;x\x07b")
    lines = task_detail_lines(
        make_task(1), notes=[], sessions=[], repo=repo, now=NOW, home=HOME, width=80
    )
    assert all("\x1b" not in plain(line) and "\x07" not in plain(line) for line in lines)
