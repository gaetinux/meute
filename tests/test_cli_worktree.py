"""`meute worktree list` and `meute worktree remove`, on throw-away repositories."""

import os
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from conftest import FAKE_CLAUDE_DIR, Sandbox
from git_support import GitRepo, fake_git, git_env, make_repo, real_git
from meute.core.db.repos import sync_repos
from meute.core.repo import NewRepo

_PINNED = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME")


def _repo(sandbox: Sandbox) -> GitRepo:
    """A known repository at `~/repo`, the sandbox's home."""
    repo = make_repo((sandbox.root / "home" / "repo").resolve(), git_env(sandbox.root))
    with sandbox.db() as db:
        _ = sync_repos(db, [NewRepo(path=repo.path, name="repo", kind=None)])
    return repo


def _add(repo: GitRepo, name: str, *extra: str) -> Path:
    path = repo.path.parent / "repo.worktrees" / name
    repo.git("worktree", "add", "--quiet", *extra, str(path), *(() if extra else ("-b", name)))
    return path


def _env(repo: GitRepo, sandbox: Sandbox) -> tuple[dict[str, str], Path]:
    """The pinned git configuration, and a `git` recording each argv before running git."""
    log = sandbox.root / "git.log"
    folder = sandbox.root / "bin"
    _ = fake_git(folder, f'printf "%s\\n" "$*" >> "{log}"\nexec "{real_git(repo)}" "$@"')
    path = f"{folder}:{FAKE_CLAUDE_DIR}:{os.environ.get('PATH', '')}"
    return {**{key: repo.env[key] for key in _PINNED}, "PATH": path}, log


def _removals(log: Path) -> list[str]:
    lines = log.read_text().splitlines() if log.exists() else []
    return [line for line in lines if "worktree remove" in line]


def _four(repo: GitRepo) -> None:
    _ = _add(repo, "feat")
    (_add(repo, "dirty") / "new.txt").write_text("new\n")
    repo.git("worktree", "lock", str(_add(repo, "pinned")))
    _ = _add(repo, "detached", "--detach")


def test_list_shows_the_linked_worktrees(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    repo = _repo(sandbox)
    _four(repo)
    env, _ = _env(repo, sandbox)
    result = sandbox.run("worktree", "list", env=env)
    assert result.returncode == 0, result.stderr
    assert "~/repo.worktrees/dirty  dirty *\n" in result.stdout
    assert result.stdout == snapshot
    alone = sandbox.run("worktree", "list", str(repo.path.parent / "repo.worktrees/feat"), env=env)
    assert alone.stdout == result.stdout


def test_list_json(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    repo = _repo(sandbox)
    _four(repo)
    env, _ = _env(repo, sandbox)
    result = sandbox.run("worktree", "list", "--json", env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.replace(str(sandbox.root), "<root>") == snapshot
    assert result.stdout.startswith('{"worktrees":[{"repo":')


def test_list_outside_git_is_refused(sandbox: Sandbox) -> None:
    plain = (sandbox.root / "home" / "plain").resolve()
    plain.mkdir(parents=True)
    result = sandbox.run("worktree", "list", str(plain))
    assert (result.returncode, result.stdout) == (1, "")
    assert result.stderr == "meute: not in a git repository: ~/plain\n"


def test_remove_a_clean_worktree_with_yes(sandbox: Sandbox) -> None:
    repo = _repo(sandbox)
    path = _add(repo, "feat")
    env, log = _env(repo, sandbox)
    result = sandbox.run("worktree", "remove", str(path), "--yes", env=env)
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == "worktree removed: ~/repo.worktrees/feat\n"
    assert not path.exists()
    assert repo.git("branch", "--list", "feat") == "  feat\n"
    assert [line.split("worktree ")[1] for line in _removals(log)] == [f"remove {path}"]


def test_remove_asks_first(sandbox: Sandbox) -> None:
    repo = _repo(sandbox)
    path = _add(repo, "feat")
    env, log = _env(repo, sandbox)
    no = sandbox.run("worktree", "remove", str(path), env=env, stdin="n\n")
    assert no.stderr == "remove worktree ~/repo.worktrees/feat? (branch feat is kept) y/n "
    assert (no.returncode, no.stdout, _removals(log)) == (0, "Cancelled.\n", [])
    yes = sandbox.run("worktree", "remove", str(path), env=env, stdin="y\n")
    assert yes.stdout == "worktree removed: ~/repo.worktrees/feat\n"
    assert not path.exists()


def test_changes_are_refused_without_force_then_removed_with_it(sandbox: Sandbox) -> None:
    repo = _repo(sandbox)
    path = _add(repo, "dirty")
    for number in range(12):
        (path / f"{number:02}.txt").write_text("new\n")
    env, log = _env(repo, sandbox)
    refused = sandbox.run("worktree", "remove", str(path), "--yes", env=env)
    assert refused.returncode == 1
    assert refused.stderr == (
        "meute: ~/repo.worktrees/dirty has uncommitted changes or unpushed commits\n"
    )
    assert refused.stdout.splitlines() == [
        *(f"?? {number:02}.txt" for number in range(10)),
        "… and 2 more",
    ]
    assert (path.is_dir(), _removals(log)) == (True, [])

    asked = sandbox.run("worktree", "remove", str(path), "--force", env=env, stdin="n\n")
    assert asked.stderr == "remove anyway? y/n "
    assert asked.stdout.splitlines()[-1] == "Cancelled."
    assert (path.is_dir(), _removals(log)) == (True, [])

    forced = sandbox.run("worktree", "remove", str(path), "--force", "--yes", env=env)
    assert forced.returncode == 0, forced.stderr
    assert forced.stdout.splitlines()[-1] == "worktree removed: ~/repo.worktrees/dirty"
    assert not path.exists()
    assert repo.git("branch", "--list", "dirty") == "  dirty\n"
    assert [line.split("worktree ")[1] for line in _removals(log)] == [f"remove --force {path}"]


@pytest.mark.parametrize("case", ["main", "locked", "live"])
def test_refusals_never_call_worktree_remove(sandbox: Sandbox, case: str) -> None:
    repo = _repo(sandbox)
    path = _add(repo, "feat")
    (path / "sub").mkdir()
    env, log = _env(repo, sandbox)
    folder = repo.path if case == "main" else path
    if case == "locked":
        repo.git("worktree", "lock", str(path))
    if case == "live":
        started = sandbox.run("session", "new", "--kind", "bash", "--cwd", str(path / "sub"))
        assert started.returncode == 0, started.stderr
    result = sandbox.run("worktree", "remove", str(folder), "--force", "--yes", env=env)
    assert result.returncode == 1
    assert (
        result.stderr
        == {
            "main": "meute: not a linked worktree: ~/repo\n",
            "locked": "meute: the worktree is locked\n",
            "live": "meute: a live session works in this worktree\n",
        }[case]
    )
    assert (path.is_dir(), _removals(log)) == (True, [])


def test_list_survives_an_absent_locked_worktree(sandbox: Sandbox) -> None:
    repo = _repo(sandbox)
    _ = _add(repo, "feat")
    away = _add(repo, "away")
    repo.git("worktree", "lock", str(away))
    away.rename(sandbox.root / "moved")
    env, _ = _env(repo, sandbox)
    result = sandbox.run("worktree", "list", env=env)
    assert (result.returncode, result.stderr) == (0, "")
    assert result.stdout == (
        "~/repo.worktrees/away  away  locked  missing\n~/repo.worktrees/feat  feat\n"
    )
    listed = sandbox.run("worktree", "list", "--json", env=env)
    assert (listed.returncode, listed.stderr) == (0, "")
    assert listed.stdout.replace(str(repo.path), "<repo>") == (
        '{"worktrees":['
        '{"repo":"<repo>","path":"<repo>.worktrees/away","branch":"away",'
        '"dirty":false,"locked":true,"missing":true},'
        '{"repo":"<repo>","path":"<repo>.worktrees/feat","branch":"feat",'
        '"dirty":false,"locked":false,"missing":false}]}\n'
    )


def test_a_failing_repository_does_not_hide_the_others(sandbox: Sandbox) -> None:
    repo = _repo(sandbox)
    _ = _add(repo, "feat")
    broken = (sandbox.root / "home" / "broken").resolve()
    broken.mkdir()
    with sandbox.db() as db:
        _ = sync_repos(db, [NewRepo(path=broken, name="broken", kind=None)])
    env, _ = _env(repo, sandbox)
    result = sandbox.run("worktree", "list", env=env)
    assert result.returncode == 1
    assert result.stdout == "~/repo.worktrees/feat  feat\n"
    assert result.stderr.startswith("meute: ~/broken: git: ")
    assert result.stderr.count("\n") == 1
