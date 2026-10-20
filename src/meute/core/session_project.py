"""The project a session belongs to."""

from collections.abc import Mapping, Sequence

from meute.core.project import ProjectRef, RepoId
from meute.core.repo import Repo
from meute.core.session import Session


def session_project(
    session: Session, *, projects: Sequence[ProjectRef], repos: Mapping[RepoId, Repo]
) -> ProjectRef | None:
    """Return the project of `session`: its own, else the one named like its repository.

    Names are compared ignoring case. Returns `None` when neither matches.
    """
    for project in projects:
        if project.id == session.project_id:
            return project
    repo = None if session.repo_id is None else repos.get(session.repo_id)
    if repo is None:
        return None
    key = repo.name.casefold()
    return next((p for p in projects if p.name.casefold() == key), None)
