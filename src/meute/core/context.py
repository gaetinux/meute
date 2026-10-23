"""The context appended to the system prompt of a Claude session."""

from meute.core.project import Project
from meute.core.task import TaskId

CONTRADICTION_RULE = (
    "The repository's `CLAUDE.md` files are authoritative on code conventions. "
    "The task is authoritative on the goal. If they contradict each other, "
    "point it out to the user instead of choosing."
)


def task_line(task_id: TaskId) -> str:
    """Return the sentence that tells a session which task it works on."""
    return (
        f"You are working on task #{task_id}. Read it with the `task_read` tool "
        "and report your progress with `task_note_add`."
    )


def work_on_task_text(task_id: TaskId) -> str:
    """Return the text pasted into a session launched for a task."""
    return f"Work on task #{task_id}."


def _level(title: str, instructions: str) -> str | None:
    text = instructions.strip()
    return f"{title}\n{text}" if text else None


def compose_context(
    *, global_instructions: str, project: Project | None, task_id: TaskId | None
) -> str | None:
    """Return the text to append to the system prompt, or None when no level has content.

    The blocks are the resolution rule, the global instructions, the project instructions and
    the task line, separated by a blank line; an empty block is omitted. Instructions are kept
    as written, minus their leading and trailing whitespace.
    """
    levels = (
        _level("Global instructions:", global_instructions),
        None
        if project is None
        else _level(f"Project instructions ({project.name}):", project.instructions),
        None if task_id is None else task_line(task_id),
    )
    blocks = [block for block in levels if block is not None]
    if not blocks:
        return None
    return "\n\n".join([CONTRADICTION_RULE, *blocks])
