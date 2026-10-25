"""The project a session belongs to."""

from collections.abc import Mapping, Sequence
from typing import Protocol

from meute.core.project import ProjectId, ProjectRef, RepoId, name_key
from meute.core.repo import Repo
from meute.core.session import Session


class NamedProject(Protocol):
    """A project as `project_of` reads it: an id and a name."""

    @property
    def id(self) -> ProjectId:
        """The project's identifier."""
        ...

    @property
    def name(self) -> str:
        """The project's name."""
        ...


def project_of[P: NamedProject](
    project_id: ProjectId | None,
    repo_id: RepoId | None,
    *,
    projects: Sequence[P],
    repos: Mapping[RepoId, Repo],
) -> P | None:
    """Return the project `project_id`, else the one named like the repository `repo_id`.

    Names are compared by `name_key`. Returns `None` when neither matches.
    """
    for project in projects:
        if project.id == project_id:
            return project
    repo = None if repo_id is None else repos.get(repo_id)
    return None if repo is None else _named_like(repo, projects)


def _named_like[P: NamedProject](repo: Repo, projects: Sequence[P]) -> P | None:
    key = name_key(repo.name)
    return next((p for p in projects if name_key(p.name) == key), None)


def session_project(
    session: Session, *, projects: Sequence[ProjectRef], repos: Mapping[RepoId, Repo]
) -> ProjectRef | None:
    """Return the project of `session`: its own, else the one named like its repository.

    Names are compared by `name_key`. Returns `None` when neither matches.
    """
    return project_of(session.project_id, session.repo_id, projects=projects, repos=repos)


def repo_projects(
    links: Mapping[RepoId, ProjectId], repos: Sequence[Repo], projects: Sequence[ProjectRef]
) -> dict[RepoId, ProjectId]:
    """Return the project of each repository: its linked one, else the one named like it.

    Names are compared by `name_key`; a repository with neither is left out.
    """
    by_name: dict[str, ProjectId] = {}
    for project in reversed(projects):
        by_name[name_key(project.name)] = project.id
    result = dict(links)
    for repo in repos:
        found = by_name.get(name_key(repo.name))
        if repo.id not in result and found is not None:
            result[repo.id] = found
    return result


def launch_project_id(
    requested: ProjectId | None,
    repo: Repo | None,
    *,
    links: Mapping[RepoId, ProjectId],
    projects: Sequence[NamedProject],
) -> ProjectId | None:
    """Return the existing project a new session belongs to; None when there is none.

    In order: the `requested` project if it still exists, the project linked to `repo`, the
    project named like `repo` (compared by `name_key`).
    """
    if any(project.id == requested for project in projects):
        return requested
    if repo is None:
        return None
    linked = links.get(repo.id)
    if linked is not None:
        return linked
    named = _named_like(repo, projects)
    return None if named is None else named.id
