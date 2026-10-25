"""End-to-end tests of `meute project link` and `unlink`."""

import json
from pathlib import Path

from conftest import Sandbox
from meute.core.db.projects import project_by_name
from meute.core.db.repos import list_repos, repo_project_links
from meute.core.db.sessions import list_sessions


def _repo(sandbox: Sandbox, root: str, name: str) -> Path:
    path = sandbox.root / "home" / root / name
    (path / ".git").mkdir(parents=True)
    (path / "package.json").write_text("")
    return path


def _scan(sandbox: Sandbox, *roots: str) -> None:
    value = json.dumps([str(sandbox.root / "home" / root) for root in roots])
    assert sandbox.run("config", "set", "repos.roots", value).returncode == 0
    assert sandbox.run("repo", "list").returncode == 0


def _setup(sandbox: Sandbox) -> Path:
    web = _repo(sandbox, "git", "web")
    _ = _repo(sandbox, "git", "api")
    _scan(sandbox, "git")
    assert sandbox.run("project", "add", "api").returncode == 0
    return web


def _launch(sandbox: Sandbox, folder: Path) -> str:
    with sandbox.db() as db:
        before = {s.id for s in list_sessions(db)}
    result = sandbox.run("session", "new", "--kind", "bash", "--cwd", str(folder))
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (newest,) = (s for s in list_sessions(db) if s.id not in before)
        assert newest.project_id is not None
        names = {p: n for n in ("web", "api") if (p := project_by_name(db, n)) is not None}
        return next(name for project, name in names.items() if project.id == newest.project_id)


def test_link_moves_the_repository_and_new_sessions_follow(sandbox: Sandbox) -> None:
    web = _setup(sandbox)
    assert _launch(sandbox, web) == "web"
    result = sandbox.run("project", "link", "api", "web")
    assert (result.returncode, result.stdout) == (0, "Linked: web → api\n")
    with sandbox.db() as db:
        api = project_by_name(db, "api")
        (web_repo,) = (r for r in list_repos(db) if r.name == "web")
        assert api is not None
        assert repo_project_links(db) == {web_repo.id: api.id}
    assert _launch(sandbox, web) == "api"
    again = sandbox.run("project", "link", "api", "web")
    assert (again.returncode, again.stdout) == (0, "Linked: web → api\n")
    with sandbox.db() as db:
        assert list(repo_project_links(db).values()) == [api.id]


def test_unlink_goes_back_to_the_project_named_like_the_repository(sandbox: Sandbox) -> None:
    web = _setup(sandbox)
    assert _launch(sandbox, web) == "web"
    assert sandbox.run("project", "link", "api", "web").returncode == 0
    result = sandbox.run("project", "unlink", "api", "web")
    assert (result.returncode, result.stdout) == (0, "Unlinked: web from api\n")
    assert _launch(sandbox, web) == "web"


def test_unlink_without_a_link_fails(sandbox: Sandbox) -> None:
    _ = _setup(sandbox)
    result = sandbox.run("project", "unlink", "api", "web")
    assert (result.returncode, result.stderr) == (1, "meute: web is not linked to api\n")


def test_unknown_project_is_the_error_of_require_project(sandbox: Sandbox) -> None:
    _ = _setup(sandbox)
    for command in ("link", "unlink"):
        result = sandbox.run("project", command, "nope", "web")
        assert (result.returncode, result.stderr) == (
            1,
            "meute: unknown project: nope (projects: api)\n",
        )


def test_unknown_repository(sandbox: Sandbox) -> None:
    _ = _setup(sandbox)
    result = sandbox.run("project", "link", "api", "ghost")
    assert (result.returncode, result.stderr) == (1, "meute: unknown repository: ghost\n")


def test_the_name_ignores_case_and_outer_spaces(sandbox: Sandbox) -> None:
    _ = _setup(sandbox)
    result = sandbox.run("project", "link", "api", " WEB ")
    assert (result.returncode, result.stdout) == (0, "Linked: web → api\n")


def test_an_ambiguous_name_lists_the_paths_and_a_path_works(sandbox: Sandbox) -> None:
    first = _repo(sandbox, "git", "web")
    second = _repo(sandbox, "work", "web")
    _scan(sandbox, "git", "work")
    assert sandbox.run("project", "add", "api").returncode == 0
    result = sandbox.run("project", "link", "api", "web")
    assert (result.returncode, result.stderr) == (
        1,
        f"meute: ambiguous repository web: {first}, {second} (give its path)\n",
    )
    by_path = sandbox.run("project", "link", "api", str(second))
    assert (by_path.returncode, by_path.stdout) == (0, "Linked: web → api\n")
    with sandbox.db() as db:
        (linked,) = (r for r in list_repos(db) if r.path == second.resolve())
        assert list(repo_project_links(db)) == [linked.id]


def test_a_path_that_is_no_known_repository(sandbox: Sandbox) -> None:
    _ = _setup(sandbox)
    elsewhere = sandbox.root / "elsewhere/web"
    result = sandbox.run("project", "link", "api", str(elsewhere))
    assert (result.returncode, result.stderr) == (
        1,
        f"meute: unknown repository: {elsewhere}\n",
    )


def test_an_escape_sequence_in_a_repository_name_is_neutralised(sandbox: Sandbox) -> None:
    _ = _setup(sandbox)
    result = sandbox.run("project", "link", "api", "x\x1b[31m")
    assert result.returncode == 1
    assert "\x1b" not in result.stderr
    assert "unknown repository: x�[31m" in result.stderr


def test_link_scans_only_when_the_database_misses_the_repository(sandbox: Sandbox) -> None:
    _ = _setup(sandbox)
    _ = _repo(sandbox, "git", "late")
    assert sandbox.run("project", "link", "api", "web").returncode == 0
    with sandbox.db() as db:
        assert sorted(r.name for r in list_repos(db)) == ["api", "web"]
    result = sandbox.run("project", "link", "api", "late")
    assert (result.returncode, result.stdout) == (0, "Linked: late → api\n")


def test_unlink_never_scans(sandbox: Sandbox) -> None:
    _ = _setup(sandbox)
    _ = _repo(sandbox, "git", "late")
    result = sandbox.run("project", "unlink", "api", "late")
    assert (result.returncode, result.stderr) == (1, "meute: unknown repository: late\n")
    with sandbox.db() as db:
        assert sorted(r.name for r in list_repos(db)) == ["api", "web"]
