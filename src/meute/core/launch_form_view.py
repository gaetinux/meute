"""The lines of the launch form (`N`)."""

from pathlib import Path

from meute.core.launch_form import FormField, LaunchForm, shares_folder
from meute.core.paths import display_path
from meute.core.session import AgentKind
from meute.core.sessions_view_text import RISKY_MODES
from meute.core.styled import Role, Span, StyledLine, clip
from meute.core.task import task_label
from meute.core.text import printable

_LABEL_WIDTH = 10
_HEADING = "── New session "
_WARNING = "⚠ another live session works in this folder"
_HELP = "Enter launch · Tab next · ←→ choose · Esc cancel"
_LEFT = "◂ "
_RIGHT = " ▸"


def _label(form: LaunchForm, field: FormField) -> Span:
    role = Role.TITLE if form.field is field else Role.DIM
    return Span(field.name.capitalize().ljust(_LABEL_WIDTH), role)


def _choice(
    form: LaunchForm, field: FormField, text: str, width: int, role: Role = Role.PLAIN
) -> StyledLine:
    """Return a row `label ◂ value ▸`, the value cut so the marks always show."""
    room = width - _LABEL_WIDTH - len(_LEFT) - len(_RIGHT)
    value = clip((Span(text, role),), room) if room > 0 else (Span(text, role),)
    return (_label(form, field), Span(_LEFT), *value, Span(_RIGHT))


def _text_row(form: LaunchForm, field: FormField, text: str) -> StyledLine:
    return (_label(form, field), Span(printable(text)))


def _folder_text(folder: str, home: Path) -> str:
    """Show a canonical absolute folder with `~`; what is being typed stays as typed."""
    path = Path(folder)
    return display_path(path, home) if folder == str(path) else folder


def _task_text(form: LaunchForm) -> str:
    if form.task is None:
        return "none"
    task = form.tasks[form.task]
    return f"{task_label(task.id)} {printable(task.title)}"


def form_lines(form: LaunchForm, *, home: Path, width: int) -> list[StyledLine]:
    """Return the form as lines of at most `width` characters."""
    heading = _HEADING + "─" * max(width - len(_HEADING), 0)
    repo = "none" if form.repo is None else printable(form.repos[form.repo].name)
    agent = "Claude" if form.agent is AgentKind.CLAUDE else "Bash"
    lines: list[StyledLine] = [
        (Span(heading, Role.ACCENT),),
        _choice(form, FormField.TYPE, agent, width),
        _choice(form, FormField.REPO, repo, width),
        _text_row(form, FormField.FOLDER, _folder_text(form.folder, home)),
        _text_row(form, FormField.TITLE, form.title),
    ]
    if form.agent is AgentKind.CLAUDE:
        mode = form.modes[form.mode]
        risky = Role.RISKY if mode in RISKY_MODES else Role.PLAIN
        lines.append(_choice(form, FormField.TASK, _task_text(form), width))
        lines.append(_choice(form, FormField.MODE, printable(mode), width, risky))
    if shares_folder(form, home):
        lines.append((Span(_WARNING, Role.WARN),))
    if form.error is not None:
        lines.append((Span(f"Error: {printable(form.error)}", Role.HIGH),))
    lines.append((Span(_HELP, Role.DIM),))
    return [clip(line, width) for line in lines]
