"""End-to-end tests of `meute repo list`."""

import json

from conftest import Sandbox
from support import load_json


def _setup(sandbox: Sandbox) -> None:
    git = sandbox.root / "home/git"
    for name, marker in (("front", "package.json"), ("api", "Cargo.toml")):
        (git / name / ".git").mkdir(parents=True)
        (git / name / marker).write_text("")
    roots = json.dumps([str(git)])
    assert sandbox.run("config", "set", "repos.roots", roots).returncode == 0


def test_repo_list_scans_configured_roots(sandbox: Sandbox) -> None:
    _setup(sandbox)
    result = sandbox.run("repo", "list")
    assert (result.returncode, result.stdout) == (
        0,
        "api  rust  ~/git/api\nfront  node  ~/git/front\n",
    )


def test_repo_list_json_is_an_array_of_repos(sandbox: Sandbox) -> None:
    _setup(sandbox)
    root = str(sandbox.root / "home/git")
    repos = load_json(sandbox.run("repo", "list", "--json").stdout)
    assert isinstance(repos, list)
    assert [(r["name"], r["kind"], r["path"]) for r in repos if isinstance(r, dict)] == [
        ("api", "rust", f"{root}/api"),
        ("front", "node", f"{root}/front"),
    ]
    first = repos[0]
    assert isinstance(first, dict)
    assert set(first) == {"id", "path", "name", "kind", "discovered_at"}


def test_repo_list_with_missing_root_is_empty(sandbox: Sandbox) -> None:
    result = sandbox.run("repo", "list")
    assert (result.returncode, result.stdout) == (0, "")
    assert sandbox.run("repo", "list", "--json").stdout == "[]\n"
