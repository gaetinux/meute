"""End-to-end tests of the project commands."""

from conftest import Sandbox


def test_project_add_and_list(sandbox: Sandbox) -> None:
    assert sandbox.run("project", "add", "zeta").stdout == "Project created: zeta\n"
    sandbox.run("project", "add", "alpha", "--description", "d")
    assert sandbox.run("project", "list").stdout == "alpha\nzeta\n"
    assert '"name":"alpha"' in sandbox.run("project", "list", "--json").stdout


def test_duplicate_project_exits_1(sandbox: Sandbox) -> None:
    sandbox.run("project", "add", "Meute")
    result = sandbox.run("project", "add", "meute")
    assert (result.returncode, result.stderr) == (1, "meute: project already exists: meute\n")
