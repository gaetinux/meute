"""`repo_holding`, adoption and `session new` for folders in linked worktrees."""

from datetime import UTC, datetime
from pathlib import Path

from conftest import Sandbox
from git_support import GitRepo, git_env, make_repo
from meute.core.db.repos import sync_repos
from meute.core.db.sessions import list_sessions
from meute.core.orphans import Orphan, adoption
from meute.core.project import RepoId
from meute.core.repo import NewRepo, Repo, repo_holding
from meute.core.session import NewSession

_AT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
_ID = "11111111-1111-4111-8111-111111111111"


def _repo(repo_id: int, path: str) -> Repo:
    return Repo(id=RepoId(repo_id), path=Path(path), name="r", kind=None, discovered_at=_AT)


def test_the_longest_nested_repository_wins() -> None:
    repos = (_repo(1, "/srv"), _repo(2, "/srv/x"), _repo(3, "/other"))
    assert repo_holding(Path("/srv/x/sub"), repos, None) == repos[1]


def test_a_linked_worktree_outside_the_repository_falls_back_to_the_main_repository() -> None:
    repos = (_repo(1, "/srv/main"), _repo(2, "/other"))
    found = repo_holding(Path("/wt/feature"), repos, Path("/srv/main"))
    assert found == repos[0]


def test_the_folder_itself_beats_the_main_repository() -> None:
    repos = (_repo(1, "/srv/main"), _repo(2, "/wt"))
    assert repo_holding(Path("/wt/feature"), repos, Path("/srv/main")) == repos[1]


def test_an_unknown_folder_has_no_repository() -> None:
    assert repo_holding(Path("/nowhere"), (_repo(1, "/srv"),), None) is None
    assert repo_holding(Path("/nowhere"), (_repo(1, "/srv"),), Path("/elsewhere")) is None


def test_adoption_of_an_orphan_in_a_linked_worktree() -> None:
    orphan = Orphan(meute_id=_ID, pane_id="%1", command="bash", cwd="/wt/feature", dead=False)
    found = adoption(orphan, (_repo(7, "/srv/main"),), Path("/srv/main"))
    assert isinstance(found, NewSession)
    assert found.repo_id == RepoId(7)


def _worktree(repo: GitRepo, name: str) -> Path:
    path = repo.path.parent / name
    repo.git("worktree", "add", "--quiet", "-b", name, str(path))
    return path.resolve()


def test_session_new_in_a_linked_worktree_records_the_main_repository(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    repo = make_repo(sandbox.root / "main", git_env(tmp_path))
    worktree = _worktree(repo, "feature")
    with sandbox.db() as db:
        (known,) = sync_repos(db, [NewRepo(path=repo.path.resolve(), name="main", kind=None)])
    result = sandbox.run("session", "new", "--kind", "bash", "--cwd", str(worktree))
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (session,) = list_sessions(db)
    assert session.repo_id == known.id
