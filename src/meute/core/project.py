"""Projects."""

from dataclasses import dataclass
from datetime import datetime
from typing import NewType

from meute.core.instants import format_instant
from meute.core.json_types import JsonObject

ProjectId = NewType("ProjectId", int)
RepoId = NewType("RepoId", int)


@dataclass(frozen=True, slots=True, kw_only=True)
class Project:
    """A project grouping tasks."""

    id: ProjectId
    name: str
    description: str
    instructions: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectRef:
    """A lightweight reference to a project."""

    id: ProjectId
    name: str


def project_to_json(project: Project) -> JsonObject:
    """Return the JSON form of `project`."""
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "instructions": project.instructions,
        "created_at": format_instant(project.created_at),
    }
