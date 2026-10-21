"""The session type `n` launches: the last one used in a repository."""

from typing import TYPE_CHECKING

from meute.core.project import RepoId
from meute.core.session import AgentKind

if TYPE_CHECKING:
    from meute.core.board_view import BoardData


def last_agent(data: "BoardData", repo_id: RepoId | None, own: AgentKind | None) -> AgentKind:
    """Return the type of session to launch in `repo_id`.

    The database's last session of the repository decides; failing that, the most recent
    of the board's sessions (live or ended) there; failing that, Claude. A session without
    a repository (`repo_id` None) relaunches its `own` type, Claude when unknown.
    """
    if repo_id is None:
        return AgentKind.CLAUDE if own is None else own
    known = data.last_agents.get(repo_id)
    if known is not None:
        return known
    sessions = [
        row.session for row in (*data.sessions, *data.ended) if row.session.repo_id == repo_id
    ]
    if not sessions:
        return AgentKind.CLAUDE
    return max(sessions, key=lambda session: (session.created_at, session.id)).agent
