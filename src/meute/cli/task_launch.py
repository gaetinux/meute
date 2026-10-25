"""Launching Claude on a task: its repository, linked to it, "Work on task #N." pasted unsent."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from meute.cli.context import CliContext
from meute.cli.session_launch_claude import ClaudeLaunch, launch_claude
from meute.cli.session_show import show_session, unreachable
from meute.cli.tmux_env import TmuxEnv
from meute.core.context import work_on_task_text
from meute.core.db.claude_sessions import get_claude_details
from meute.core.db.repos import list_repos
from meute.core.db.task_reads import project_repo_ids
from meute.core.db.tasks import get_task
from meute.core.errors import InvalidInput
from meute.core.paths import make_private_dir
from meute.core.project import RepoId, name_key
from meute.core.repo import Repo
from meute.core.session import SessionId
from meute.core.task import Task, TaskId, task_label
from meute.core.text import one_line
from meute.tmux.panes import pane_of_session, paste_text

READY_TIMEOUT_SECONDS = 10.0
READY_POLL_SECONDS = 0.2
# Spike S8: Claude accepts a bracketed paste right after SessionStart; 0.5 s is the margin.
PASTE_DELAY_SECONDS = 0.5
_TITLE_WIDTH = 40


def _task_repo(task: Task, repos: Mapping[RepoId, Repo], project_repos: Sequence[RepoId]) -> Repo:
    for repo_id in (task.repo_id, *project_repos):
        if repo_id is not None and repo_id in repos:
            return repos[repo_id]
    if task.project is not None:
        key = name_key(task.project.name)
        named = next((r for r in repos.values() if name_key(r.name) == key), None)
        if named is not None:
            return named
    message = f"{task_label(task.id)} has no repository: set one on the task or its project"
    raise InvalidInput(message)


def task_launch_folder(
    task: Task, repos: Mapping[RepoId, Repo], project_repos: Sequence[RepoId]
) -> Path:
    """Return the task's repository, else the first of its project, else the one named like it.

    Names are compared ignoring case and surrounding spaces.

    Raises:
        InvalidInput: neither the task nor its project has a known repository.
    """
    return _task_repo(task, repos, project_repos).path


def launch_on_task(  # noqa: PLR0913 — signature of the plan: the clock is injected for the tests
    ctx: CliContext,
    env: TmuxEnv,
    task_id: TaskId,
    environ: Mapping[str, str],
    *,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> bool:
    """Start Claude on a task, show it, and paste `Work on task #N.` into its input, unsent.

    The line waits for Claude to be ready (its SessionStart hook); `False` when it was not
    within 10 s: the session stays, nothing is pasted. The task itself is never changed.

    Raises:
        InvalidInput: the task has no repository, `claude` is missing, or the session has no
            pane; nothing was started in the first two cases.
        NotFound: no such task.
        TmuxError: tmux failed.
    """
    task = get_task(ctx.db, task_id)
    text = work_on_task_text(task_id)
    project_repos = [] if task.project is None else project_repo_ids(ctx.db, task.project.id)
    repo = _task_repo(task, {r.id: r for r in list_repos(ctx.db)}, project_repos)
    title = one_line(f"{task_label(task.id)} {task.title}", _TITLE_WIDTH, ellipsis=True)
    request = ClaudeLaunch(cwd=repo.path, title=title, repo_id=repo.id, task_id=task.id)
    return _launch_and_paste(ctx, env, request, text, environ, monotonic=monotonic, sleep=sleep)


def launch_claude_on_task(  # noqa: PLR0913 — like `launch_on_task`, with the form's request
    ctx: CliContext,
    env: TmuxEnv,
    request: ClaudeLaunch,
    task_id: TaskId,
    environ: Mapping[str, str],
    *,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> bool:
    """Start Claude as `request` says, linked to a task, and paste `Work on task #N.`, unsent.

    The launch form's way of `launch_on_task`: its folder, title and mode are kept, and the
    text waits for SessionStart the same way; `False` when Claude was not ready within 10 s.

    Raises:
        InvalidInput: the folder does not exist, `claude` is missing, the mode is unknown, or
            the session has no pane.
        NotFound: no such task; nothing was started.
        TmuxError: tmux failed.
    """
    _ = get_task(ctx.db, task_id)  # NotFound before anything starts
    text = work_on_task_text(task_id)
    linked = replace(request, task_id=task_id)
    return _launch_and_paste(ctx, env, linked, text, environ, monotonic=monotonic, sleep=sleep)


def _launch_and_paste(  # noqa: PLR0913 — the launch, its text, and the injected clock
    ctx: CliContext,
    env: TmuxEnv,
    request: ClaudeLaunch,
    text: str,
    environ: Mapping[str, str],
    *,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> bool:
    """Launch and show Claude, then paste `text` once it is ready; `False` if it never was."""
    session = launch_claude(ctx, env, request, environ)
    show_session(ctx, env, session.id)
    if not _wait_until_ready(ctx, session.id, monotonic=monotonic, sleep=sleep):
        return False
    sleep(PASTE_DELAY_SECONDS)
    pane = pane_of_session(env.tmux, session.id)
    if pane is None:
        raise unreachable(session.title)
    make_private_dir(ctx.paths.state_dir)
    paste_text(env.tmux, pane.id, text, private_dir=ctx.paths.state_dir)
    return True


def _wait_until_ready(
    ctx: CliContext,
    session_id: SessionId,
    *,
    monotonic: Callable[[], float],
    sleep: Callable[[float], None],
) -> bool:
    """Reread the session until SessionStart gave it a native id, for at most 10 s."""
    deadline = monotonic() + READY_TIMEOUT_SECONDS
    while get_claude_details(ctx.db, session_id).native_id is None:
        if monotonic() >= deadline:
            return False
        sleep(READY_POLL_SECONDS)
    return True
