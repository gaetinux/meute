"""Creating a worktree for a launch: its checks in order, then `git worktree add`."""

from pathlib import Path

import pytest

from git_support import GitRepo, fake_git, real_git
from meute.cli.context import ENVIRONMENT_ERRORS
from meute.cli.worktree_launch import create_worktree, launch_in_new_worktree
from meute.core.errors import InvalidInput, MeuteError
from meute.git.run import GitError
from meute.git.worktree import list_worktrees_text

# Every name `branch_error` refuses (tests/test_worktrees.py).
REFUSED = ["-x", "--force", "a..b", "feat/", "a b", "a\nb", "../../etc", "x.lock",
           "", "/abs", "a//b", "a\\b", "a~b", "a^b", "a:b", "a?b", "a*b", "a[b",
           "a@{b", "a/./b", "a/..", ".", "a.", "a\x7fb", "a\tb"]  # fmt: skip


def witness(folder: Path) -> tuple[Path, Path]:
    """A fake `git` in `folder` that records each argv in a log and fails; and that log."""
    log = folder / "git.log"
    _ = fake_git(folder, f'printf "%s\\n" "$*" >> "{log}"\nexit 1')
    return folder, log


def files_below(folder: Path) -> set[Path]:
    return set(folder.rglob("*"))


def test_the_worktree_is_created_from_head(git_repo: GitRepo) -> None:
    path = create_worktree(git_repo.env, git_repo.path, "feat/x")
    assert path == git_repo.path.parent / "repo.worktrees" / "feat" / "x"
    assert (path / "README.md").read_text() == "hello\n"
    assert git_repo.git("rev-parse", "feat/x") == git_repo.git("rev-parse", "HEAD")
    assert git_repo.git("status", "--porcelain") == ""
    assert not (git_repo.path / ".gitignore").exists()


def test_an_existing_branch_is_told_by_git(git_repo: GitRepo) -> None:
    git_repo.git("branch", "x")
    with pytest.raises(MeuteError, match=r"^git: fatal: a branch named 'x' already exists$"):
        _ = create_worktree(git_repo.env, git_repo.path, "x")
    assert not (git_repo.path.parent / "repo.worktrees" / "x").exists()


def test_a_name_git_refuses_never_reaches_worktree_add(git_repo: GitRepo) -> None:
    with pytest.raises(MeuteError, match=r"^git: fatal: '?a/\.b'? is not a valid branch name"):
        _ = create_worktree(git_repo.env, git_repo.path, "a/.b")
    assert not (git_repo.path.parent / "repo.worktrees").exists()


def test_an_existing_folder_is_refused_without_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = tmp_path / "repo"
    (repo.parent / "repo.worktrees" / "x").mkdir(parents=True)
    folder, log = witness(tmp_path / "bin")
    with pytest.raises(InvalidInput, match=r"^folder already exists: ~/repo\.worktrees/x$"):
        _ = create_worktree({"PATH": str(folder)}, repo, "x")
    assert not log.exists()


def test_a_dangling_link_counts_as_an_existing_folder(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (tmp_path / "repo.worktrees").mkdir()
    (tmp_path / "repo.worktrees" / "x").symlink_to(tmp_path / "elsewhere")
    folder, log = witness(tmp_path / "bin")
    with pytest.raises(InvalidInput, match=r"^folder already exists: "):
        _ = create_worktree({"PATH": str(folder)}, repo, "x")
    assert not log.exists()
    assert not (tmp_path / "elsewhere").exists()


def test_a_linked_folder_on_the_way_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (tmp_path / "repo.worktrees").mkdir()
    (tmp_path / "outside").mkdir()
    (tmp_path / "repo.worktrees" / "feat").symlink_to(tmp_path / "outside")
    folder, log = witness(tmp_path / "bin")
    with pytest.raises(InvalidInput, match=r"^folder already exists: .*/repo\.worktrees/feat$"):
        _ = create_worktree({"PATH": str(folder)}, repo, "feat/x")
    assert not log.exists()
    assert list((tmp_path / "outside").iterdir()) == []


@pytest.mark.parametrize("branch", REFUSED)
def test_a_refused_name_creates_nothing_and_runs_no_git(tmp_path: Path, branch: str) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    folder, log = witness(tmp_path / "bin")
    before = files_below(tmp_path)
    with pytest.raises(InvalidInput):
        _ = create_worktree({"PATH": str(folder)}, repo, branch)
    assert not log.exists()
    assert files_below(tmp_path) == before


def test_without_git(tmp_path: Path) -> None:
    with pytest.raises(MeuteError, match=r"^git not found$"):
        _ = create_worktree({"PATH": str(tmp_path)}, tmp_path / "repo", "x")


def test_a_failed_launch_keeps_the_worktree(git_repo: GitRepo) -> None:
    def launch(path: Path) -> None:
        assert path.is_dir()
        message = "claude not found"
        raise InvalidInput(message)

    path = git_repo.path.parent / "repo.worktrees" / "x"
    with pytest.raises(MeuteError) as raised:
        launch_in_new_worktree(git_repo.env, git_repo.path, "x", launch)
    assert str(raised.value) == (
        f"worktree created at {path} but the launch failed: claude not found"
    )
    assert path.is_dir()


def test_a_successful_launch_gets_the_new_folder(git_repo: GitRepo) -> None:
    def launch(path: Path) -> Path:
        return path

    path = launch_in_new_worktree(git_repo.env, git_repo.path, "x", launch)
    assert path == git_repo.path.parent / "repo.worktrees" / "x"


def test_a_failed_creation_launches_nothing(git_repo: GitRepo) -> None:
    calls: list[Path] = []
    git_repo.git("branch", "x")
    with pytest.raises(MeuteError, match=r"^git: "):
        launch_in_new_worktree(git_repo.env, git_repo.path, "x", calls.append)
    assert calls == []


def test_the_worktree_list_is_read(git_repo: GitRepo) -> None:
    path = create_worktree(git_repo.env, git_repo.path, "x")
    text = list_worktrees_text(real_git(git_repo), git_repo.path, timeout=5, environ=git_repo.env)
    assert f"worktree {path}\n" in text
    assert "branch refs/heads/x\n" in text


def test_git_errors_are_environment_errors() -> None:
    assert GitError in ENVIRONMENT_ERRORS
