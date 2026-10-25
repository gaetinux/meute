"""Live preview of a quick entry: what `Title @project ! >due` would create."""

import difflib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import assert_never

from meute.core.errors import InvalidInput
from meute.core.project import ProjectId, ProjectRef, name_key
from meute.core.quick_add import parse_quick_add
from meute.core.status import Priority
from meute.core.styled import Role, Span, StyledLine, labelled
from meute.core.task import Due
from meute.core.text import one_line, printable
from meute.core.views import format_due

FLOATING_NAME = "none"
_CUTOFF = 0.6
_SHOWN = 200
_LABEL_WIDTH = 10


class PreviewError(StrEnum):
    """Why a quick entry cannot be created; the value is the text shown."""

    EMPTY_TITLE = "empty title"
    UNKNOWN_PROJECT = "unknown project"


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


@dataclass(frozen=True, slots=True)
class NewFromRepo:
    """`@name` matches no project but the repository `name`: creating makes its project."""

    name: str


ProjectChoice = Named | Displayed | Floating | NewFromRepo | UnknownProject


def choice_project_id(choice: ProjectChoice) -> ProjectId | NewFromRepo | None:
    """Return the id of the project `choice` names; None when the task floats.

    A project still to create from a repository is returned as is.

    Raises:
        InvalidInput: the project is unknown (`unknown project: {name}`, then ` ({close}?)`
            when a project has a close name).
    """
    match choice:
        case Named(project=ref) | Displayed(project=ref):
            return ref.id
        case Floating():
            return None
        case NewFromRepo():
            return choice
        case UnknownProject(name=name, suggestion=suggestion):
            hint = "" if suggestion is None else f" ({suggestion}?)"
            message = f"{PreviewError.UNKNOWN_PROJECT}: {name.strip()}{hint}"
            raise InvalidInput(message)
        case _:
            assert_never(choice)


@dataclass(frozen=True, slots=True, kw_only=True)
class QuickPreview:
    """What a quick entry would create; `title` is None while nothing is typed."""

    title: str | None
    project: ProjectChoice
    priority: Priority
    due: Due | None
    error: PreviewError | None

    @property
    def can_create(self) -> bool:
        """Whether the entry can be created as typed."""
        return self.error is None and self.title is not None


def resolve_quick_project(
    name: str | None,
    default: ProjectRef | None,
    projects: Sequence[ProjectRef],
    repo_names: Sequence[str] = (),
) -> ProjectChoice:
    """Resolve the `@name` of a quick entry (None when absent) against `projects`.

    `@none` floats, a name matches ignoring case and outer spaces, no `@` takes `default`.
    A name matching no project but one of `repo_names` makes the project of that repository.
    """
    if name is None:
        return Floating(explicit=False) if default is None else Displayed(default)
    key = name_key(name)
    if key == FLOATING_NAME:
        return Floating(explicit=True)
    for project in projects:
        if name_key(project.name) == key:
            return Named(project)
    for repo_name in repo_names:
        if name_key(repo_name) == key:
            return NewFromRepo(repo_name.strip())
    names = [*(p.name for p in projects), *repo_names]
    close = difflib.get_close_matches(key, [name_key(n) for n in names], n=1, cutoff=_CUTOFF)
    suggestion = next((n for n in names if close and name_key(n) == close[0]), None)
    return UnknownProject(name=name, suggestion=suggestion)


def quick_preview(
    text: str,
    *,
    now: datetime,
    default: ProjectRef | None,
    projects: Sequence[ProjectRef],
    repo_names: Sequence[str] = (),
) -> QuickPreview:
    """Preview `text` as a quick entry, `@name` as `resolve_quick_project` says; never raises."""
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
            error=PreviewError.EMPTY_TITLE,
        )
    project = resolve_quick_project(parsed.project, default, projects, repo_names)
    return QuickPreview(
        title=parsed.title,
        project=project,
        priority=parsed.priority,
        due=parsed.due,
        error=PreviewError.UNKNOWN_PROJECT if isinstance(project, UnknownProject) else None,
    )


def _row(label: str, *value: Span) -> StyledLine:
    return labelled(label, _LABEL_WIDTH, *value)


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
        case NewFromRepo(name=name):
            return _row(
                "Project",
                Span(one_line(name, _SHOWN), Role.KIND),
                Span("  (new project from repository)", Role.DIM),
            )
        case UnknownProject(name=name, suggestion=suggestion):
            hint = () if suggestion is None else (Span(f" ({one_line(suggestion, _SHOWN)}?)"),)
            text = f"@{one_line(name, _SHOWN)}: {PreviewError.UNKNOWN_PROJECT}"
            return _row("Project", Span(text, Role.HIGH), *hint)
        case _:
            assert_never(project)


def _footer(preview: QuickPreview) -> StyledLine:
    if preview.can_create:
        return (Span("Enter create · Esc cancel", Role.DIM),)
    if preview.error is PreviewError.UNKNOWN_PROJECT:
        text = "Cannot create: fix the project or use @none · Esc cancel"
    else:
        text = f"Cannot create: {PreviewError.EMPTY_TITLE} · Esc cancel"
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
