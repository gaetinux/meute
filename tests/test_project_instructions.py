"""`set_project_instructions` and `meute project edit` / `show`."""

from pathlib import Path

import pytest

from conftest import Sandbox
from meute.core.db.connection import Database
from meute.core.db.projects import create_project, project_by_name, set_project_instructions
from meute.core.errors import NotFound
from meute.core.project import ProjectId
from support import load_json


def test_set_and_clear_instructions(db: Database) -> None:
    project = create_project(db, "meute")
    updated = set_project_instructions(db, project.id, "Use uv.")
    assert updated.instructions == "Use uv."
    stored = project_by_name(db, "meute")
    assert stored is not None
    assert stored.instructions == "Use uv."
    assert set_project_instructions(db, project.id, "").instructions == ""


def test_set_instructions_of_unknown_project(db: Database) -> None:
    with pytest.raises(NotFound):
        set_project_instructions(db, ProjectId(99), "x")


def test_edit_with_text(sandbox: Sandbox) -> None:
    sandbox.run("project", "add", "meute")
    result = sandbox.run("project", "edit", "meute", "--instructions", "Use uv.")
    assert (result.returncode, result.stderr) == (0, "")
    assert "instructions: Use uv.\n" in sandbox.run("project", "show", "meute").stdout


def test_edit_with_file(sandbox: Sandbox, tmp_path: Path) -> None:
    sandbox.run("project", "add", "meute")
    file = tmp_path / "rules.md"
    file.write_text("Été\nline two\n", encoding="utf-8")
    assert sandbox.run("project", "edit", "meute", "--instructions-file", str(file)).returncode == 0
    shown = load_json(sandbox.run("project", "show", "meute", "--json").stdout)
    assert isinstance(shown, dict)
    assert shown["instructions"] == "Été\nline two\n"


def test_edit_with_empty_text_clears(sandbox: Sandbox) -> None:
    sandbox.run("project", "add", "meute")
    sandbox.run("project", "edit", "meute", "--instructions", "x")
    sandbox.run("project", "edit", "meute", "--instructions", "")
    shown = load_json(sandbox.run("project", "show", "meute", "--json").stdout)
    assert isinstance(shown, dict)
    assert shown["instructions"] == ""


@pytest.mark.parametrize("extra", [[], ["--instructions", "a", "--instructions-file", "f"]])
def test_edit_needs_exactly_one_option(sandbox: Sandbox, extra: list[str]) -> None:
    sandbox.run("project", "add", "meute")
    result = sandbox.run("project", "edit", "meute", *extra)
    assert (result.returncode, result.stderr) == (
        1,
        "meute: give --instructions or --instructions-file\n",
    )


def test_edit_with_missing_file(sandbox: Sandbox, tmp_path: Path) -> None:
    sandbox.run("project", "add", "meute")
    missing = tmp_path / "nope.md"
    result = sandbox.run("project", "edit", "meute", "--instructions-file", str(missing))
    assert result.returncode == 1
    assert result.stderr.startswith("meute: cannot read ")


def test_edit_unknown_project(sandbox: Sandbox) -> None:
    result = sandbox.run("project", "edit", "nope", "--instructions", "x")
    assert result.returncode == 4


def test_show_text(sandbox: Sandbox) -> None:
    sandbox.run("project", "add", "meute", "--description", "The app")
    sandbox.run("project", "edit", "meute", "--instructions", "a\nb\x1b[31m")
    out = sandbox.run("project", "show", "meute").stdout
    assert out == "name: meute\ndescription: The app\ninstructions: a\nb�[31m\nrepos:\n"


def test_show_json_and_unknown(sandbox: Sandbox) -> None:
    sandbox.run("project", "add", "meute")
    shown = load_json(sandbox.run("project", "show", "meute", "--json").stdout)
    assert shown == {"name": "meute", "description": "", "instructions": "", "repos": []}
    assert sandbox.run("project", "show", "nope").returncode == 4
