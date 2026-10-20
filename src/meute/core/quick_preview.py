"""Live preview of a quick entry: what `Title @project ! >due` would create."""

import difflib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import assert_never

from meute.core.errors import InvalidInput
from meute.core.project import ProjectRef
from meute.core.quick_add import parse_quick_add
from meute.core.status import Priority
from meute.core.styled import Role, Span, StyledLine
from meute.core.task import Due
from meute.core.text import one_line, printable
from meute.core.views import format_due

FLOATING_NAME = "none"
_CUTOFF = 0.6
_SHOWN = 200
_LABEL_WIDTH = 10


@dataclass(frozen=True, slots=True)
class Named:
    """The entry names this project (`@name`)."""

    project: ProjectRef


@dataclass(frozen=True, slots=True)
class Displayed:
    """No `@`: the project of the displayed session."""

    project: ProjectRef


@dataclass(frozen=True, slots=True)
class Floating:
    """The task has no project; `explicit` is true for `@none`."""

    explicit: bool


@dataclass(frozen=True, slots=True)
class UnknownProject:
    """`@name` matches no project; `suggestion` is the closest name, if any."""

    name: str
    suggestion: str | None


ProjectChoice = Named | Displayed | Floating | UnknownProject


@dataclass(frozen=True, slots=True, kw_only=True)
class QuickPreview:
    """What a quick entry would create; `title` is None while nothing is typed."""

    title: str | None
    project: ProjectChoice
    priority: Priority
    due: Due | None
    error: str | None

    @property
    def can_create(self) -> bool:
        """Whether the entry can be created as typed."""
        return self.error is None and self.title is not None


def _key(name: str) -> str:
    return name.strip().casefold()


def resolve_quick_project(
    name: str | None, default: ProjectRef | None, projects: Sequence[ProjectRef]
) -> ProjectChoice:
    """Resolve the `@name` of a quick entry (None when absent) against `projects`.

    `@none` floats, a name matches ignoring case and outer spaces, no `@` takes `default`.
    """
    if name is None:
        return Floating(explicit=False) if default is None else Displayed(default)
    key = _key(name)
    if key == FLOATING_NAME:
        return Floating(explicit=True)
    for project in projects:
        if _key(project.name) == key:
            return Named(project)
    close = difflib.get_close_matches(key, [_key(p.name) for p in projects], n=1, cutoff=_CUTOFF)
    suggestion = next((p.name for p in projects if close and _key(p.name) == close[0]), None)
    return UnknownProject(name=name, suggestion=suggestion)


def quick_preview(
    text: str, *, now: datetime, default: ProjectRef | None, projects: Sequence[ProjectRef]
) -> QuickPreview:
    """Preview `text` as a quick entry; never raises."""
    if not text.strip():
        return QuickPreview(
            title=None,
            project=resolve_quick_project(None, default, projects),
            priority=Priority.NORMAL,
            due=None,
            error=None,
        )
    try:
        parsed = parse_quick_add(text, now)
    except InvalidInput:
        return QuickPreview(
            title=None,
            project=resolve_quick_project(None, default, projects),
            priority=Priority.NORMAL,
            due=None,
            error="empty title",
        )
    project = resolve_quick_project(parsed.project, default, projects)
    return QuickPreview(
        title=parsed.title,
        project=project,
        priority=parsed.priority,
        due=parsed.due,
        error="unknown project" if isinstance(project, UnknownProject) else None,
    )


def _row(label: str, *value: Span) -> StyledLine:
    return (Span(label.ljust(_LABEL_WIDTH), Role.DIM), *value)


def _project_line(project: ProjectChoice) -> StyledLine:
    match project:
        case Named(project=ref):
            return _row("Project", Span(one_line(ref.name, _SHOWN), Role.KIND))
        case Displayed(project=ref):
            return _row(
                "Project",
                Span(one_line(ref.name, _SHOWN), Role.KIND),
                Span("  (displayed session · @none: floating)", Role.DIM),
            )
        case Floating(explicit=explicit):
            note = () if explicit else (Span("  (no displayed session)", Role.DIM),)
            return _row("Project", Span("floating", Role.KIND), *note)
        case UnknownProject(name=name, suggestion=suggestion):
            hint = () if suggestion is None else (Span(f" ({one_line(suggestion, _SHOWN)}?)"),)
            text = f"@{one_line(name, _SHOWN)}: unknown project"
            return _row("Project", Span(text, Role.HIGH), *hint)
        case _:
            assert_never(project)


def _footer(preview: QuickPreview) -> StyledLine:
    if preview.can_create:
        return (Span("Enter create · Esc cancel", Role.DIM),)
    if preview.error == "unknown project":
        text = "Cannot create: fix the project or use @none · Esc cancel"
    else:
        text = "Cannot create: empty title · Esc cancel"
    return (Span(text, Role.HIGH),)


def preview_lines(preview: QuickPreview, now: datetime) -> list[StyledLine]:
    """Return the lines that show `preview`, ending with the available keys."""
    lines: list[StyledLine] = []
    if preview.title is not None:
        lines.append(_row("Title", Span(printable(preview.title), Role.TITLE)))
    lines.append(_project_line(preview.project))
    if preview.priority is not Priority.NORMAL:
        role = Role.HIGH if preview.priority is Priority.URGENT else Role.WARN
        lines.append(_row("Priority", Span(preview.priority.value, role)))
    if preview.due is not None:
        lines.append(_row("Due", Span(printable(format_due(preview.due, now)))))
    lines.append(_footer(preview))
    return lines
