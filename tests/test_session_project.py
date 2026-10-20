"""The project of a session: its own project, else the project named like its repository."""

from dataclasses import replace
from pathlib import Path

from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.session_project import session_project
from support import BOARD_SESSION_A, board_repo

_MEUTE = ProjectRef(id=ProjectId(1), name="meute")
_NOTES = ProjectRef(id=ProjectId(2), name="Notes")
_REPOS = {RepoId(1): board_repo(1, "meute", None), RepoId(2): board_repo(2, "notes", None)}


def test_the_session_project_id_wins() -> None:
    session = replace(BOARD_SESSION_A, project_id=ProjectId(2), repo_id=RepoId(1))
    assert session_project(session, projects=[_MEUTE, _NOTES], repos=_REPOS) == _NOTES


def test_falls_back_to_the_project_named_like_the_repository() -> None:
    session = replace(BOARD_SESSION_A, repo_id=RepoId(2))
    assert session_project(session, projects=[_MEUTE, _NOTES], repos=_REPOS) == _NOTES


def test_an_unknown_project_id_falls_back_to_the_repository_name() -> None:
    session = replace(BOARD_SESSION_A, project_id=ProjectId(9), repo_id=RepoId(1))
    assert session_project(session, projects=[_MEUTE], repos=_REPOS) == _MEUTE


def test_no_project_when_nothing_matches() -> None:
    assert session_project(BOARD_SESSION_A, projects=[_MEUTE], repos=_REPOS) is None
    lost = replace(BOARD_SESSION_A, repo_id=RepoId(7), cwd=Path("/srv"))
    assert session_project(lost, projects=[_MEUTE], repos=_REPOS) is None
    other = replace(BOARD_SESSION_A, repo_id=RepoId(1))
    assert session_project(other, projects=[_NOTES], repos=_REPOS) is None
