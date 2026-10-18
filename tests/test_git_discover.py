import os
from pathlib import Path

import pytest

from meute.git.discover import DEFAULT_DEPTH, DiscoveredRepo, discover, expand_home
from meute.git.kind import RepoKind


def repo(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path


def names(found: list[DiscoveredRepo]) -> list[str]:
    return [item.name for item in found]


def test_default_depth_is_three() -> None:
    assert DEFAULT_DEPTH == 3


def test_finds_repos_up_to_depth_three(tmp_path: Path) -> None:
    root = tmp_path / "r"
    for relative in ("a", "x/b", "x/y/c", "x/y/z/d"):
        repo(root / relative)
    assert names(discover([root])) == ["a", "b", "c"]


def test_max_depth_is_a_parameter(tmp_path: Path) -> None:
    root = tmp_path / "r"
    repo(root / "a")
    repo(root / "x/b")
    assert names(discover([root], max_depth=1)) == ["a"]


def test_root_itself_can_be_a_repo(tmp_path: Path) -> None:
    root = repo(tmp_path / "r")
    (root / "Cargo.toml").write_text("")
    found = discover([root], max_depth=0)
    assert found == [
        DiscoveredRepo(path=root.resolve(), name="r", kind=RepoKind.RUST, worktrees=())
    ]


def test_does_not_descend_into_repos(tmp_path: Path) -> None:
    root = tmp_path / "r"
    repo(root / "a")
    repo(root / "a/sub")
    assert names(discover([root])) == ["a"]


def test_results_are_sorted_and_deduplicated(tmp_path: Path) -> None:
    root = tmp_path / "r"
    repo(root / "b")
    repo(root / "a")
    found = discover([root, root, root / "a"])
    assert [item.path for item in found] == [(root / "a").resolve(), (root / "b").resolve()]


@pytest.mark.parametrize("relative", [False, True])
def test_worktrees_attach_to_their_main_repo(tmp_path: Path, relative: bool) -> None:  # noqa: FBT001 — parametrized flag
    root = tmp_path / "r"
    main = repo(root / "meute")
    (main / ".git" / "worktrees" / "feat").mkdir(parents=True)
    worktree = root / "meute.worktrees" / "feat"
    worktree.mkdir(parents=True)
    admin = main.resolve() / ".git" / "worktrees" / "feat"
    target = os.path.relpath(admin, worktree.resolve()) if relative else str(admin)
    (worktree / ".git").write_text(f"gitdir: {target}\n")
    found = discover([root])
    assert names(found) == ["meute"]
    assert found[0].worktrees == (worktree.resolve(),)


def test_orphan_worktree_and_submodule_are_ignored(tmp_path: Path) -> None:
    root = tmp_path / "r"
    repo(root / "a")
    orphan = root / "orphan"
    orphan.mkdir()
    (orphan / ".git").write_text(f"gitdir: {tmp_path}/gone/.git/worktrees/orphan\n")
    sub = root / "sub"
    sub.mkdir()
    (sub / ".git").write_text("gitdir: ../a/.git/modules/sub\n")
    garbage = root / "garbage"
    garbage.mkdir()
    (garbage / ".git").write_text("nonsense\n")
    found = discover([root])
    assert names(found) == ["a"]
    assert found[0].worktrees == ()


def test_missing_root_symlink_loop_and_unreadable_folder_are_harmless(tmp_path: Path) -> None:
    assert discover([tmp_path / "absent"]) == []
    root = tmp_path / "r"
    repo(root / "a")
    (root / "loop").symlink_to(root)
    locked = root / "locked"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        assert names(discover([root])) == ["a"]
    finally:
        locked.chmod(0o700)


def test_symlinked_repo_is_not_followed(tmp_path: Path) -> None:
    outside = repo(tmp_path / "outside")
    root = tmp_path / "r"
    root.mkdir()
    (root / "link").symlink_to(outside)
    assert discover([root]) == []


def test_non_utf8_names_are_skipped(tmp_path: Path) -> None:
    root = tmp_path / "r"
    repo(root / "a")
    repo(root / os.fsdecode(b"\xff"))
    assert names(discover([root])) == ["a"]


def test_hidden_node_modules_target_and_venv_are_skipped(tmp_path: Path) -> None:
    root = tmp_path / "r"
    for skipped in (".hidden", "node_modules", "target", ".venv"):
        repo(root / skipped / "inner")
    repo(root / "ok")
    assert names(discover([root])) == ["ok"]


@pytest.mark.parametrize(
    ("root", "home", "expected"),
    [
        ("~", Path("/h"), Path("/h")),
        ("~/git", Path("/h"), Path("/h/git")),
        ("/abs", Path("/h"), Path("/abs")),
        ("~other", Path("/h"), Path("~other")),
        ("~", None, Path("~")),
        ("~/git", None, Path("~/git")),
    ],
)
def test_expand_home(root: str, home: Path | None, expected: Path) -> None:
    assert expand_home(root, home) == expected
