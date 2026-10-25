"""`launch_project_id`: which existing project a new session in a repository belongs to."""

from datetime import UTC, datetime
from pathlib import Path

from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.repo import Repo
from meute.core.session_project import launch_project_id

WEB = RepoId(1)
FRONT = ProjectRef(id=ProjectId(1), name="front")
WEB_PROJECT = ProjectRef(id=ProjectId(2), name="web")


def _repo(name: str) -> Repo:
    return Repo(
        id=WEB,
        path=Path("/r") / name,
        name=name,
        kind=None,
        discovered_at=datetime(2026, 10, 14, tzinfo=UTC),
    )


def test_the_requested_project_wins_over_the_link_and_the_name() -> None:
    found = launch_project_id(
        FRONT.id,
        _repo("web"),
        links={WEB: FRONT.id},
        projects=[FRONT, WEB_PROJECT],
    )
    assert found == FRONT.id
    other = launch_project_id(
        WEB_PROJECT.id, _repo("web"), links={WEB: FRONT.id}, projects=[FRONT, WEB_PROJECT]
    )
    assert other == WEB_PROJECT.id


def test_a_requested_project_that_no_longer_exists_is_ignored() -> None:
    found = launch_project_id(ProjectId(99), _repo("web"), links={}, projects=[WEB_PROJECT])
    assert found == WEB_PROJECT.id


def test_the_link_wins_over_the_name() -> None:
    found = launch_project_id(
        None, _repo("web"), links={WEB: FRONT.id}, projects=[FRONT, WEB_PROJECT]
    )
    assert found == FRONT.id


def test_the_name_ignores_case_and_spaces() -> None:
    assert (
        launch_project_id(None, _repo(" Web "), links={}, projects=[WEB_PROJECT]) == WEB_PROJECT.id
    )


def test_nothing_found_is_none() -> None:
    assert launch_project_id(None, _repo("api"), links={}, projects=[FRONT]) is None
    assert launch_project_id(None, None, links={}, projects=[FRONT]) is None
