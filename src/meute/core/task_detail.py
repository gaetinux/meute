"""The detail lines under the list of the Tasks tab."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from meute.core.paths import display_path
from meute.core.repo import Repo
from meute.core.session import Session
from meute.core.session_state import state_label
from meute.core.sessions_view_text import STATE_SYMBOLS, state_role
from meute.core.status import Blocked, status_text
from meute.core.styled import Role, Span, StyledLine, clip, labelled
from meute.core.task import Note, Task, task_label
from meute.core.task_line import due_short
from meute.core.text import one_line, printable
from meute.core.views import MONTHS, format_due

_LIMIT = 1000
_NOTES_SHOWN = 2
_SEPARATOR = " · "
_LABEL_WIDTH = 9


def _header(task: Task, width: int) -> StyledLine:
    text = f"─ {task_label(task.id)} {one_line(task.title, _LIMIT)} "
    return (Span(text.ljust(width, "─")[:width], Role.ACCENT),)


def _status(task: Task, now: datetime) -> StyledLine:
    line: list[Span] = [
        Span(one_line(status_text(task.status), _LIMIT)),
        Span(f"{_SEPARATOR}priority ", Role.DIM),
        Span(task.priority.value),
    ]
    if task.due is not None:
        line += [Span(f"{_SEPARATOR}due ", Role.DIM), Span(format_due(task.due, now))]
        short = due_short(task, now)
        # A blocked task already shows its reason in the status.
        if short is not None and not isinstance(task.status, Blocked):
            line += [Span(" ("), Span(short[0], short[1]), Span(")")]
    return labelled("Status", _LABEL_WIDTH, *line)


def _project(task: Task, repo: Repo | None, home: Path | None) -> StyledLine:
    if task.project is None:
        line = [Span("floating", Role.DIM)]
    else:
        line = [Span(one_line(task.project.name, _LIMIT), Role.KIND)]
    if repo is not None:
        line.append(Span(f"{_SEPARATOR}repo {printable(display_path(repo.path, home))}", Role.DIM))
    return labelled("Project", _LABEL_WIDTH, *line)


def _about(task: Task) -> StyledLine | None:
    lines = task.description.strip().splitlines()
    if not lines:
        return None
    return labelled("About", _LABEL_WIDTH, Span(one_line(lines[0], _LIMIT)))


def _note_when(note: Note, now: datetime) -> str:
    local = note.created_at.astimezone(now.tzinfo)
    if local.date() == now.date():
        return f"{local:%H:%M}"
    return f"{MONTHS[local.month - 1]} {local.day:02d}"


def _notes(notes: Sequence[Note], now: datetime) -> list[StyledLine]:
    latest = sorted(notes, key=lambda note: (note.created_at, note.id), reverse=True)
    return [
        labelled(
            "Notes" if index == 0 else "",
            _LABEL_WIDTH,
            Span(f"{_note_when(note, now)} ", Role.DIM),
            Span(one_line(note.body, _LIMIT)),
        )
        for index, note in enumerate(latest[:_NOTES_SHOWN])
    ]


def _sessions(sessions: Sequence[Session]) -> StyledLine:
    line: list[Span] = []
    for index, session in enumerate(sessions):
        role = state_role(session.state)
        if index:
            line.append(Span(_SEPARATOR, Role.DIM))
        line += [
            Span(f"{STATE_SYMBOLS[role]} ", role),
            Span(one_line(session.title, _LIMIT)),
            Span(f" {state_label(session.state)}", Role.DIM),
        ]
    return labelled("Sessions", _LABEL_WIDTH, *line)


def task_detail_lines(  # noqa: PLR0913 — one keyword per piece of data shown
    task: Task,
    *,
    notes: Sequence[Note],
    sessions: Sequence[Session],
    repo: Repo | None,
    now: datetime,
    home: Path | None,
    width: int,
) -> list[StyledLine]:
    """Return the detail of `task`: a rule with its title, then at most six lines of facts.

    Status, project (and repo), the first line of the description, the two latest notes
    (time when from today, else `Mon DD`) and the linked sessions are shown when known.
    Each line is cut to `width`.
    """
    lines: list[StyledLine] = [_header(task, width), _status(task, now), _project(task, repo, home)]
    if (about := _about(task)) is not None:
        lines.append(about)
    lines += _notes(notes, now)
    if sessions:
        lines.append(_sessions(sessions))
    return [lines[0], *(clip(line, width) for line in lines[1:])]
