"""Checking a linked worktree before it is removed, then removing it with the branch kept."""

from pathlib import Path

import pytest

from git_support import GitRepo, fake_git, git_env, make_repo, real_git
from meute.cli.board_git import CliBoardGit
from meute.cli.worktree_removal import inspect_worktree, remove_checked
from meute.core.errors import InvalidInput, MeuteError
from meute.core.worktrees import WorktreeCheck, listed_text
from meute.git.worktree import remove_worktree


def linked(repo: GitRepo, name: str = "feat", *extra: str) -> Path:
    """Add the worktree `<repo>.worktrees/<name>` on a new branch `name`; return its folder."""
    path = repo.path.parent / "repo.worktrees" / name
    repo.git("worktree", "add", "--quiet", *extra, str(path), *(() if extra else ("-b", name)))
    return path


def recording(folder: Path, repo: GitRepo) -> tuple[dict[str, str], Path]:
    """An environment whose `git` records each argv in a log, then runs the real git."""
    log = folder / "git.log"
    _ = fake_git(folder, f'printf "%s\\n" "$*" >> "{log}"\nexec "{real_git(repo)}" "$@"')
    return {**repo.env, "PATH": str(folder)}, log


def removals(log: Path) -> list[str]:
    """The `worktree remove` commands in a recording log."""
    lines = log.read_text().splitlines() if log.exists() else []
    return [line for line in lines if "worktree remove" in line]


def commit(folder: Path, repo: GitRepo, name: str) -> None:
    (folder / name).write_text(f"{name}\n")
    repo.git("-C", str(folder), "add", name)
    repo.git("-C", str(folder), "commit", "--quiet", f"--message=add {name}")


@pytest.fixture
def repo(tmp_path: Path) -> GitRepo:
    return make_repo(tmp_path / "repo", git_env(tmp_path))


def test_a_clean_worktree_has_nothing_to_report(repo: GitRepo) -> None:
    path = linked(repo)
    assert inspect_worktree(repo.env, path, ()) == WorktreeCheck(
        path=path.resolve(),
        repo=repo.path.resolve(),
        branch="feat",
        locked=False,
        changes=(),
        commits=(),
    )


def test_changes_are_reported(repo: GitRepo) -> None:
    path = linked(repo)
    (path / "README.md").write_text("changed\n")
    (path / "new.txt").write_text("new\n")
    check = inspect_worktree(repo.env, path, ())
    assert (check.changes, check.commits, check.clean) == (
        (" M README.md", "?? new.txt"),
        (),
        False,
    )


def test_a_commit_only_this_worktree_has_is_reported(repo: GitRepo) -> None:
    path = linked(repo)
    commit(path, repo, "a.txt")
    short = repo.git("-C", str(path), "rev-parse", "--short", "HEAD").strip()
    check = inspect_worktree(repo.env, path, ())
    assert (check.changes, check.commits) == ((), (f"{short} add a.txt",))


def test_a_commit_also_on_another_branch_is_not_reported(repo: GitRepo) -> None:
    path = linked(repo)
    commit(path, repo, "a.txt")
    repo.git("branch", "other", "feat")
    assert inspect_worktree(repo.env, path, ()).clean


def test_a_detached_head_counts_every_branch(repo: GitRepo) -> None:
    path = linked(repo, "detached", "--detach")
    check = inspect_worktree(repo.env, path, ())
    assert (check.branch, check.clean) == (None, True)
    commit(path, repo, "a.txt")
    assert len(inspect_worktree(repo.env, path, ()).commits) == 1


def test_many_commits_keep_their_count(repo: GitRepo) -> None:
    path = linked(repo)
    for number in range(12):
        commit(path, repo, f"{number}.txt")
    check = inspect_worktree(repo.env, path, ())
    assert len(check.commits) == 12
    shown = listed_text(check.commits)
    assert shown[0].endswith(" add 11.txt")
    assert shown[-1] == "… and 2 more"


def test_the_log_never_shows_signatures(repo: GitRepo, tmp_path: Path) -> None:
    path = linked(repo)
    commit(path, repo, "a.txt")
    environ, log = recording(tmp_path / "bin", repo)
    _ = inspect_worktree(environ, path, ())
    logs = [line for line in log.read_text().splitlines() if " log " in f" {line} "]
    assert logs
    assert all("-c log.showSignature=false" in line and "--no-walk" in line for line in logs)


def test_a_missing_folder_is_refused(repo: GitRepo, tmp_path: Path) -> None:
    with pytest.raises(InvalidInput, match=r"^folder not found: "):
        _ = inspect_worktree(repo.env, tmp_path / "missing", ())


@pytest.mark.parametrize("where", ["main", "nested", "plain", "inside"])
def test_what_is_not_a_linked_worktree_is_refused(
    repo: GitRepo, tmp_path: Path, where: str
) -> None:
    path = linked(repo)
    (repo.path / "src").mkdir()
    (path / "sub").mkdir()
    (tmp_path / "plain").mkdir()
    folder = {
        "main": repo.path,
        "nested": repo.path / "src",
        "plain": tmp_path / "plain",
        "inside": path / "sub",
    }[where]
    with pytest.raises(InvalidInput, match=r"^not a linked worktree: "):
        _ = inspect_worktree(repo.env, folder, ())


def test_a_locked_worktree_is_refused(repo: GitRepo) -> None:
    path = linked(repo)
    repo.git("worktree", "lock", str(path))
    with pytest.raises(InvalidInput, match=r"^the worktree is locked$"):
        _ = inspect_worktree(repo.env, path, ())


def test_a_live_session_in_a_subfolder_is_refused(repo: GitRepo, tmp_path: Path) -> None:
    path = linked(repo)
    (path / "sub").mkdir()
    (tmp_path / "link").symlink_to(path / "sub")
    with pytest.raises(InvalidInput, match=r"^a live session works in this worktree$"):
        _ = inspect_worktree(repo.env, path, [tmp_path / "link"])
    assert inspect_worktree(repo.env, path, [repo.path, tmp_path / "missing"]).clean


def test_without_git_it_says_so(repo: GitRepo, tmp_path: Path) -> None:
    path = linked(repo)
    with pytest.raises(MeuteError, match=r"^git not found$"):
        _ = inspect_worktree({"PATH": str(tmp_path)}, path, ())


def test_remove_keeps_the_branch(repo: GitRepo, tmp_path: Path) -> None:
    path = linked(repo)
    commit(path, repo, "a.txt")
    head = repo.git("rev-parse", "feat")
    environ, log = recording(tmp_path / "bin", repo)
    remove_worktree(Path(environ["PATH"]) / "git", repo.path, path, force=False, environ=environ)
    assert not path.exists()
    assert repo.git("rev-parse", "feat") == head
    assert [line.split("worktree ")[1] for line in removals(log)] == [f"remove {path}"]


def test_force_is_passed_once(repo: GitRepo, tmp_path: Path) -> None:
    path = linked(repo)
    (path / "new.txt").write_text("new\n")
    environ, log = recording(tmp_path / "bin", repo)
    remove_worktree(Path(environ["PATH"]) / "git", repo.path, path, force=True, environ=environ)
    assert not path.exists()
    assert [line.split("worktree ")[1] for line in removals(log)] == [f"remove --force {path}"]


def test_remove_checked_refuses_changes_without_force(repo: GitRepo, tmp_path: Path) -> None:
    path = linked(repo)
    (path / "new.txt").write_text("new\n")
    environ, log = recording(tmp_path / "bin", repo)
    check = inspect_worktree(environ, path, ())
    with pytest.raises(InvalidInput, match=r"has uncommitted changes or unpushed commits"):
        remove_checked(environ, check, force=False)
    assert path.is_dir()
    assert removals(log) == []
    remove_checked(environ, check, force=True)
    assert not path.exists()


def test_board_git_inspects_with_the_live_folders(repo: GitRepo) -> None:
    path = linked(repo)
    live: list[Path] = []
    git = CliBoardGit(repo.env, live_folders=lambda: live)
    assert isinstance(git.inspect(path), WorktreeCheck)
    live.append(path / ".")
    assert git.inspect(path) == "a live session works in this worktree"
    refused = git.inspect(repo.path)
    assert isinstance(refused, str)
    assert refused.startswith("not a linked worktree: ")
    assert CliBoardGit({"PATH": "/nonexistent"}).inspect(path) == "git not found"
