"""The state of the launch form (`N`): its fields, its moves and the launch it asks for."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

from meute.core.board_actions import LaunchBash, LaunchClaude
from meute.core.board_entries import BoardEntry, OrphanEntry, RepoEntry, SessionEntry
from meute.core.board_view import BoardData
from meute.core.config_validate import PERMISSION_MODES
from meute.core.last_agent import last_agent
from meute.core.repo import Repo
from meute.core.session import AgentKind
from meute.core.session_state import is_live
from meute.core.status import is_open
from meute.core.task import Task
from meute.core.text import one_line
from meute.core.views import sort_for_display

if TYPE_CHECKING:
    from meute.core.project import RepoId

FOLDER_LIMIT = 4096
TITLE_LIMIT = 200


class FormField(Enum):
    """The fields of the form, in the order Tab visits them."""

    TYPE = auto()
    REPO = auto()
    FOLDER = auto()
    TITLE = auto()
    TASK = auto()
    MODE = auto()


_CLAUDE_ONLY = frozenset({FormField.TASK, FormField.MODE})
_TYPES = (AgentKind.CLAUDE, AgentKind.BASH)


@dataclass(frozen=True, slots=True, kw_only=True)
class LaunchForm:
    """What the launch form holds.

    `repo`, `task` and `mode` index `repos` (None is `none`), `tasks` (None is `none`) and
    `modes`. `busy` holds the resolved folders of the live sessions.
    """

    agent: AgentKind
    repos: tuple[Repo, ...]
    repo: int | None
    folder: str
    title: str
    tasks: tuple[Task, ...]
    task: int | None
    modes: tuple[str, ...]
    mode: int
    field: FormField
    busy: frozenset[Path]
    error: str | None


def _project_tasks(data: BoardData, repo: Repo | None, now: datetime) -> tuple[Task, ...]:
    """Return the open tasks of the project of `repo`, most urgent first."""
    project_id = None if repo is None else data.repo_projects.get(repo.id)
    if project_id is None:
        return ()
    own = (
        task
        for task in data.tasks
        if is_open(task.status) and task.project is not None and task.project.id == project_id
    )
    return tuple(sort_for_display(own, now))


def _modes(default_mode: str) -> tuple[str, ...]:
    rest = sorted(PERMISSION_MODES - {default_mode})
    return (default_mode, *rest) if default_mode in PERMISSION_MODES else tuple(rest)


def _resolved(path: Path) -> Path:
    """Return `path` resolved; one that cannot be resolved stands for itself."""
    try:
        return path.resolve()
    except (ValueError, OSError, RuntimeError):
        return path


def _busy(data: BoardData) -> frozenset[Path]:
    return frozenset(
        _resolved(row.session.cwd) for row in data.sessions if is_live(row.session.state)
    )


def open_form(
    data: BoardData, entry: BoardEntry | None, *, default_mode: str, now: datetime
) -> LaunchForm:
    """Return the form `N` opens on `entry`, prefilled; an orphan pane counts as no selection."""
    repo_id: RepoId | None = None
    folder = ""
    own = None
    task_id = None
    match entry:
        case SessionEntry():
            session = entry.row.session
            repo_id, folder, own, task_id = (
                session.repo_id,
                str(session.cwd),
                session.agent,
                session.task_id,
            )
        case RepoEntry():
            repo_id, folder = entry.repo.id, str(entry.repo.path)
        case OrphanEntry() | None:
            pass
    chosen = next((repo for repo in data.repos if repo.id == repo_id), None)
    rest = sorted(
        (repo for repo in data.repos if repo is not chosen),
        key=lambda repo: (repo.name.casefold(), str(repo.path)),
    )
    repos = rest if chosen is None else [chosen, *rest]
    tasks = _project_tasks(data, chosen, now)
    task = next((i for i, item in enumerate(tasks) if item.id == task_id), None)
    return LaunchForm(
        agent=last_agent(data, repo_id, own),
        repos=tuple(repos),
        repo=None if chosen is None else 0,
        folder=folder,
        title="",
        tasks=tasks,
        task=task,
        modes=_modes(default_mode),
        mode=0,
        field=FormField.TYPE,
        busy=_busy(data),
        error=None,
    )


def with_busy(form: LaunchForm, data: BoardData) -> LaunchForm:
    """Return `form` with the live folders of the new `data`; nothing else changes."""
    return replace(form, busy=_busy(data))


def _fields(form: LaunchForm) -> list[FormField]:
    if form.agent is AgentKind.BASH:
        return [field for field in FormField if field not in _CLAUDE_ONLY]
    return list(FormField)


def move(form: LaunchForm, step: int) -> LaunchForm:
    """Return `form` on the next field (`step` 1) or the previous one (-1), wrapping around."""
    fields = _fields(form)
    index = fields.index(form.field) if form.field in fields else 0
    return replace(form, field=fields[(index + step) % len(fields)], error=None)


def _cycle(current: int | None, step: int, count: int) -> int | None:
    """Step through `count` indexes and a final None, wrapping around."""
    position = count if current is None else current
    position = (position + step) % (count + 1)
    return None if position == count else position


def choose(form: LaunchForm, step: int, data: BoardData, now: datetime) -> LaunchForm:
    """Return `form` with the choice of its current field moved by `step`; text fields stay."""
    match form.field:
        case FormField.TYPE:
            index = _TYPES.index(form.agent)
            return replace(form, agent=_TYPES[(index + step) % len(_TYPES)], error=None)
        case FormField.REPO:
            return _choose_repo(form, step, data, now)
        case FormField.TASK:
            return replace(form, task=_cycle(form.task, step, len(form.tasks)), error=None)
        case FormField.MODE:
            return replace(form, mode=(form.mode + step) % len(form.modes), error=None)
        case FormField.FOLDER | FormField.TITLE:
            return form


def _choose_repo(form: LaunchForm, step: int, data: BoardData, now: datetime) -> LaunchForm:
    index = _cycle(form.repo, step, len(form.repos))
    if index is None:
        return replace(form, repo=None, tasks=(), task=None, error=None)
    repo = form.repos[index]
    return replace(
        form,
        repo=index,
        folder=str(repo.path),
        tasks=_project_tasks(data, repo, now),
        task=None,
        error=None,
    )


def _clean(text: str, limit: int) -> str:
    """Return `text` on one printable line, its edge spaces kept as one space each."""
    if text.isspace():
        return " "
    lead = " " if text[:1].isspace() else ""
    trail = " " if text[-1:].isspace() else ""
    return f"{lead}{one_line(text, limit)}{trail}"


def _edit_text(form: LaunchForm, edit: Callable[[str, int], str]) -> LaunchForm:
    """Return `form` with `edit(text, limit)` stored in the current text field; others stay."""
    match form.field:
        case FormField.FOLDER:
            return replace(form, folder=edit(form.folder, FOLDER_LIMIT), error=None)
        case FormField.TITLE:
            return replace(form, title=edit(form.title, TITLE_LIMIT), error=None)
        case FormField.TYPE | FormField.REPO | FormField.TASK | FormField.MODE:
            return form


def type_text(form: LaunchForm, text: str) -> LaunchForm:
    """Return `form` with `text` added to the end of the current text field."""
    return _edit_text(form, lambda current, limit: (current + _clean(text, limit))[:limit])


def erase(form: LaunchForm) -> LaunchForm:
    """Return `form` without the last character of the current text field."""
    return _edit_text(form, lambda current, _limit: current[:-1])


def _expanded(folder: str, home: Path) -> Path | str:
    """Return the typed folder as an absolute path, or the error saying why it is not one."""
    text = folder.strip()
    if not text:
        return "folder is empty"
    if text == "~":
        path = home
    elif text.startswith("~/"):
        path = home / text[2:]
    else:
        path = Path(text)
    if not path.is_absolute():
        return f"folder must be absolute: {folder.strip()}"
    return path


def form_action(form: LaunchForm, home: Path) -> LaunchBash | LaunchClaude | str:
    """Return the launch the form asks for, or the text of the error in its folder."""
    cwd = _expanded(form.folder, home)
    if isinstance(cwd, str):
        return cwd
    repo_id = None if form.repo is None else form.repos[form.repo].id
    title = form.title.strip() or None
    if form.agent is AgentKind.BASH:
        return LaunchBash(cwd=cwd, repo_id=repo_id, title=title)
    return LaunchClaude(
        cwd=cwd,
        repo_id=repo_id,
        title=title,
        task_id=None if form.task is None else form.tasks[form.task].id,
        permission_mode=form.modes[form.mode],
    )


def shares_folder(form: LaunchForm, home: Path) -> bool:
    """Return whether another live session works in the folder the form would launch in."""
    cwd = _expanded(form.folder, home)
    return not isinstance(cwd, str) and _resolved(cwd) in form.busy
