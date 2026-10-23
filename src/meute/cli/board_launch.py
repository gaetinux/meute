"""The board's launches: a Bash or Claude session in a folder, or in a new worktree."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from meute.cli.context import CliContext
from meute.cli.folder_repo import repo_id_of_folder
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_launch_claude import ClaudeLaunch, launch_claude
from meute.cli.session_show import show_session
from meute.cli.tmux_env import TmuxEnv
from meute.cli.worktree_launch import launch_in_new_worktree
from meute.core.board_view import LaunchBash, LaunchClaude
from meute.core.db.repos import list_repos
from meute.core.errors import InvalidInput
from meute.core.project import RepoId
from meute.core.task import TaskId

_NO_REPOSITORY = "a new worktree needs a repository"


@dataclass(frozen=True, slots=True, kw_only=True)
class BoardLaunch:
    """What a board launch needs; `on_task` launches Claude on a task picked in the form."""

    ctx: CliContext
    env: TmuxEnv
    environ: Mapping[str, str]
    on_task: Callable[[TaskId, ClaudeLaunch], None]

    def perform(self, action: LaunchBash | LaunchClaude) -> None:
        """Launch `action` in its folder, or in a new worktree of its repository.

        Raises:
            InvalidInput: the folder, the branch or the repository was refused.
            MeuteError: the worktree could not be created, or the launch failed after it was.
        """
        if action.new_branch is None:
            self._start(action, action.cwd, self._repo_of(action))
            return
        repo = next((r for r in list_repos(self.ctx.db) if r.id == action.repo_id), None)
        if repo is None:
            raise InvalidInput(_NO_REPOSITORY)
        launch_in_new_worktree(
            self.environ,
            repo.path,
            action.new_branch,
            lambda path: self._start(action, path, repo.id),
        )

    def _repo_of(self, action: LaunchBash | LaunchClaude) -> RepoId | None:
        """The repository of a launch: the form's, else the one holding its folder."""
        if action.repo_id is not None:
            return action.repo_id
        return repo_id_of_folder(self.ctx, action.cwd)

    def _start(self, action: LaunchBash | LaunchClaude, cwd: Path, repo_id: RepoId | None) -> None:
        ctx, env, environ = self.ctx, self.env, self.environ
        match action:
            case LaunchBash():
                request = BashLaunch(cwd=cwd, repo_id=repo_id, title=action.title)
                session = launch_bash(ctx, env, request, environ)
                show_session(ctx, env, session.id)
            case LaunchClaude():
                claude = ClaudeLaunch(
                    cwd=cwd,
                    repo_id=repo_id,
                    title=action.title,
                    permission_mode=action.permission_mode,
                    task_id=action.task_id,
                )
                if action.task_id is None:
                    session = launch_claude(ctx, env, claude, environ)
                    show_session(ctx, env, session.id)
                else:  # a task picked in the form: its text is pasted, like `L`, in a worker
                    self.on_task(action.task_id, claude)
            case _:
                assert_never(action)
