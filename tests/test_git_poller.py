"""`GitPoller`: the Git state of the board's folders, read in the background, never waited on."""

import subprocess
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from pathlib import Path

import pytest

from git_support import GitRepo, fake_git, git_env, make_repo, real_git
from meute.cli.git_poller import GitPoller
from meute.core.git_state import GitState
from support import wait_until
from test_git_run import is_alive

_STATUS = "printf '# branch.oid 0123456789abcdef\\n# branch.head main\\n'"


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _logging_git(tmp_path: Path, *, config: str = "exit 1", status: str = _STATUS) -> Path:
    """A fake git logging its subcommand to `tmp_path/log`, with a body per subcommand."""
    log = tmp_path / "log"
    return fake_git(
        tmp_path / "bin",
        f"""case "$*" in
  *" config "*) echo config >> "{log}"; {config} ;;
  *" status "*) echo status >> "{log}"; {status} ;;
  *" diff "*) echo diff >> "{log}"; printf '2\\t1\\tf\\n' ;;
esac""",
    )


def _log(tmp_path: Path) -> list[str]:
    log = tmp_path / "log"
    return log.read_text().splitlines() if log.exists() else []


@pytest.fixture
def pollers() -> Generator[list[GitPoller]]:
    """Every poller of the test, closed at its end."""
    made: list[GitPoller] = []
    yield made
    for poller in made:
        poller.close()


def _poller(
    made: list[GitPoller],
    git: Path | None,
    environ: Mapping[str, str],
    *,
    clock: Callable[[], float] = time.monotonic,
    kill_after: float = 5.0,
) -> GitPoller:
    poller = GitPoller(git, environ, every=10.0, kill_after=kill_after, monotonic=clock)
    made.append(poller)
    return poller


def _harvest(poller: GitPoller, folders: Sequence[Path]) -> Mapping[Path, GitState]:
    found: list[Mapping[Path, GitState]] = []

    def got() -> bool:
        result = poller.poll(folders)
        if result is not None:
            found.append(result)
        return bool(found)

    wait_until("the git round", got)
    return found[0]


def _state(poller: GitPoller, repo: GitRepo) -> GitState | None:
    return _harvest(poller, [repo.path]).get(repo.path)


def test_a_round_reads_status_and_numstat(git_repo: GitRepo, pollers: list[GitPoller]) -> None:
    (git_repo.path / "README.md").write_text("changed\nmore\n")
    poller = _poller(pollers, real_git(git_repo), git_repo.env)
    assert _state(poller, git_repo) == GitState(
        branch="main",
        detached=None,
        upstream=False,
        ahead=0,
        behind=0,
        dirty=True,
        added=2,
        removed=1,
    )


def test_a_folder_outside_git_is_absent(tmp_path: Path, pollers: list[GitPoller]) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    env = git_env(tmp_path)
    poller = _poller(pollers, real_git(make_repo(tmp_path / "r", env)), env)
    assert _harvest(poller, [plain]) == {}


def test_a_repo_without_commit_has_no_line_counts(tmp_path: Path, pollers: list[GitPoller]) -> None:
    repo = GitRepo(path=tmp_path / "empty", env=git_env(tmp_path))
    repo.path.mkdir()
    repo.git("init", "--quiet", "--initial-branch=main")
    (repo.path / "new.txt").write_text("a\n")
    poller = _poller(pollers, real_git(repo), repo.env)
    state = _state(poller, repo)
    assert state is not None
    assert (state.branch, state.dirty, state.added, state.removed) == ("main", True, 0, 0)


def test_a_rebase_in_progress(git_repo: GitRepo, pollers: list[GitPoller]) -> None:
    git_repo.git("checkout", "--quiet", "-b", "feat")
    (git_repo.path / "README.md").write_text("feat\n")
    git_repo.git("commit", "--quiet", "--all", "--message=feat")
    git_repo.git("checkout", "--quiet", "main")
    (git_repo.path / "README.md").write_text("main\n")
    git_repo.git("commit", "--quiet", "--all", "--message=main")
    git_repo.git("checkout", "--quiet", "feat")
    main = git_repo.git("rev-parse", "--short=7", "main").strip()
    stopped = subprocess.run(
        ["git", "-C", str(git_repo.path), "rebase", "--quiet", "main"],  # noqa: S607 — the test git
        capture_output=True,
        env=dict(git_repo.env),
        check=False,
    )
    assert stopped.returncode != 0, "the rebase must stop on its conflict"
    poller = _poller(pollers, real_git(git_repo), git_repo.env)
    state = _state(poller, git_repo)
    assert state is not None
    assert (state.branch, state.detached, state.dirty) == (None, main, True)


def test_a_submodule_is_ignored(
    git_repo: GitRepo, tmp_path: Path, pollers: list[GitPoller]
) -> None:
    sub = make_repo(tmp_path / "sub", git_repo.env)
    git_repo.git(
        "-c", "protocol.file.allow=always", "submodule", "--quiet", "add", str(sub.path), "sub"
    )
    git_repo.git("commit", "--quiet", "--message=submodule")
    (git_repo.path / "sub/README.md").write_text("changed in the submodule\n")
    poller = _poller(pollers, real_git(git_repo), git_repo.env)
    state = _state(poller, git_repo)
    assert state is not None
    assert (state.dirty, state.added, state.removed) == (False, 0, 0)


def test_a_path_with_spaces(tmp_path: Path, pollers: list[GitPoller]) -> None:
    repo = make_repo(tmp_path / "with some spaces", git_env(tmp_path))
    (repo.path / "README.md").write_text("hello\nworld\n")
    poller = _poller(pollers, real_git(repo), repo.env)
    state = _state(poller, repo)
    assert state is not None
    assert (state.branch, state.added, state.removed) == ("main", 1, 0)


def test_a_failing_diff_gives_zero_lines(tmp_path: Path, pollers: list[GitPoller]) -> None:
    git = fake_git(
        tmp_path / "bin",
        f'case "$*" in *" config "*) exit 1 ;; *" status "*) {_STATUS} ;; *) exit 128 ;; esac',
    )
    poller = _poller(pollers, git, {})
    state = _harvest(poller, [tmp_path]).get(tmp_path)
    assert state is not None
    assert (state.branch, state.added, state.removed) == ("main", 0, 0)


def test_a_shared_folder_is_read_once(tmp_path: Path, pollers: list[GitPoller]) -> None:
    poller = _poller(pollers, _logging_git(tmp_path), {})
    result = _harvest(poller, [tmp_path, tmp_path])
    assert list(result) == [tmp_path]
    assert sorted(_log(tmp_path)) == ["config", "diff", "status"]


def test_relative_or_missing_folders_start_nothing(
    tmp_path: Path, pollers: list[GitPoller]
) -> None:
    poller = _poller(pollers, _logging_git(tmp_path), {})
    assert _harvest(poller, [Path("relative"), tmp_path / "missing"]) == {}
    assert _log(tmp_path) == []


def test_at_most_forty_folders_live_first(tmp_path: Path, pollers: list[GitPoller]) -> None:
    folders = [tmp_path / f"f{index:02}" for index in range(45)]
    for folder in folders:
        folder.mkdir()
    poller = _poller(pollers, _logging_git(tmp_path), {})
    result = _harvest(poller, [folders[0], *folders])
    assert list(result) == folders[:40]
    assert _log(tmp_path).count("status") == 40


def test_without_git_nothing_runs(tmp_path: Path, pollers: list[GitPoller]) -> None:
    poller = _poller(pollers, None, {})
    for _ in range(3):
        assert poller.poll([tmp_path]) is None


def test_an_unsupported_filter_drops_the_folder(tmp_path: Path, pollers: list[GitPoller]) -> None:
    git = _logging_git(tmp_path, config=r"printf 'filter.a=b.clean\ncat\0'")
    poller = _poller(pollers, git, {})
    assert _harvest(poller, [tmp_path]) == {}
    assert _log(tmp_path) == ["config"]


def test_a_failing_lookup_drops_the_folder(tmp_path: Path, pollers: list[GitPoller]) -> None:
    poller = _poller(pollers, _logging_git(tmp_path, config="exit 128"), {})
    assert _harvest(poller, [tmp_path]) == {}
    assert _log(tmp_path) == ["config"]


def test_one_round_at_a_time(tmp_path: Path, pollers: list[GitPoller]) -> None:
    clock = _Clock()
    git = _logging_git(tmp_path, status="exec sleep 30")
    poller = _poller(pollers, git, {}, clock=clock, kill_after=100.0)
    wait_until(
        "status to start", lambda: poller.poll([tmp_path]) is None and "status" in _log(tmp_path)
    )
    clock.now += 50
    for _ in range(5):
        assert poller.poll([tmp_path]) is None
    time.sleep(0.2)
    assert _log(tmp_path).count("config") == 1


def test_no_new_round_before_every(tmp_path: Path, pollers: list[GitPoller]) -> None:
    clock = _Clock()
    poller = _poller(pollers, _logging_git(tmp_path), {}, clock=clock)
    _ = _harvest(poller, [tmp_path])
    clock.now += 9
    assert poller.poll([tmp_path]) is None
    assert _log(tmp_path).count("config") == 1
    clock.now += 1
    _ = _harvest(poller, [tmp_path])
    assert _log(tmp_path).count("config") == 2


@pytest.mark.parametrize("stage", ["config", "status"])
def test_a_sleeping_git_is_never_waited_and_killed(
    tmp_path: Path, pollers: list[GitPoller], stage: str
) -> None:
    pids = tmp_path / "pids"
    sleeping = f'echo $$ > "{pids}"; exec sleep 30'
    git = (
        _logging_git(tmp_path, config=sleeping)
        if stage == "config"
        else _logging_git(tmp_path, status=sleeping)
    )
    clock = _Clock()
    poller = _poller(pollers, git, {}, clock=clock)

    def polled_quickly() -> bool:
        started = time.monotonic()
        result = poller.poll([tmp_path])
        assert time.monotonic() - started < 0.5, "poll must never wait for git"
        assert result is None
        return pids.exists() and pids.read_text().strip() != ""

    wait_until("the sleeping git", polled_quickly)
    sleeper = int(pids.read_text())
    clock.now += 4
    assert poller.poll([tmp_path]) is None
    assert is_alive(sleeper)
    clock.now += 2  # more than kill_after since the stage started
    assert poller.poll([tmp_path]) == {}
    assert not Path(f"/proc/{sleeper}").exists()  # killed and reaped
    pids.unlink()
    clock.now += 10
    wait_until("the next round", lambda: poller.poll([tmp_path]) is None and pids.exists())
    assert _log(tmp_path).count(stage) == 2


def test_close_kills_the_running_commands(tmp_path: Path, pollers: list[GitPoller]) -> None:
    pids = tmp_path / "pids"
    git = _logging_git(tmp_path, status=f'echo $$ > "{pids}"; exec sleep 30')
    poller = _poller(pollers, git, {}, clock=_Clock())
    wait_until("status to start", lambda: poller.poll([tmp_path]) is None and pids.exists())
    wait_until("its pid", lambda: pids.read_text().strip() != "")
    sleeper = int(pids.read_text())
    poller.close()
    assert not Path(f"/proc/{sleeper}").exists()
