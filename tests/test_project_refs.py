"""Tests for the project references of the database and the project id of a quick choice."""

import pytest

from meute.core.db.connection import Database
from meute.core.db.projects import create_project, project_refs
from meute.core.errors import InvalidInput
from meute.core.project import ProjectId, ProjectRef
from meute.core.quick_preview import (
    Displayed,
    Floating,
    Named,
    UnknownProject,
    choice_project_id,
)

INFRA = ProjectRef(id=ProjectId(4), name="infra")


def test_project_refs_follow_the_name_order(db: Database) -> None:
    mods = create_project(db, "mods")
    infra = create_project(db, "Infra")
    assert project_refs(db) == (
        ProjectRef(id=infra.id, name="Infra"),
        ProjectRef(id=mods.id, name="mods"),
    )


def test_project_refs_of_an_empty_database(db: Database) -> None:
    assert project_refs(db) == ()


def test_choice_project_id() -> None:
    assert choice_project_id(Named(INFRA)) == INFRA.id
    assert choice_project_id(Displayed(INFRA)) == INFRA.id
    assert choice_project_id(Floating(explicit=True)) is None


def test_unknown_project_names_the_close_one() -> None:
    with pytest.raises(InvalidInput, match=r"^unknown project: infar \(infra\?\)$"):
        _ = choice_project_id(UnknownProject(name="infar", suggestion="infra"))
    with pytest.raises(InvalidInput, match=r"^unknown project: nope$"):
        _ = choice_project_id(UnknownProject(name="nope", suggestion=None))
