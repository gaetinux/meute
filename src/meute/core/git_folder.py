"""Which folder a session's Git state is read from, and the `where` texts of its card."""

from pathlib import Path

from meute.core.git_state import GitState, git_text
from meute.core.session import Session
from meute.core.statusline import StatuslineData


def git_folder(session: Session, metrics: StatuslineData | None) -> Path:
    """Return the folder whose Git state a session shows.

    That is the absolute worktree path Claude reported, else the session's folder.
    """
    if metrics is not None and metrics.worktree_path:
        path = Path(metrics.worktree_path)
        if path.is_absolute():
            return path
    return session.cwd


def where_texts(git: GitState | None, metrics: StatuslineData, last_tool: str | None) -> list[str]:
    """Return the texts of line 3 of a card, to be joined: Git state or branch, then the tool.

    With a Git state, the Claude worktree name follows it; without, the worktree branch
    stands alone, as before.
    """
    if git is None:
        return [text for text in (metrics.worktree_branch, last_tool) if text]
    return [text for text in (git_text(git), metrics.worktree_name, last_tool) if text]
