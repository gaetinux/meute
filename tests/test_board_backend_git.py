"""`CliBoardBackend` and the Git state of its sessions' folders."""

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from git_support import GitRepo, fake_git, real_git
from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.git_poller import GitPoller
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.tmux_env import TmuxEnv
from meute.core.git_state import GitState
from support import wait_until
from test_board_backend import _ENVIRON, _Clock, ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixtures reused

if TYPE_CHECKING:
    from collections.abc import Mapping

_CHANGED = GitState(
    branch="main", detached=None, upstream=False, ahead=0, behind=0, dirty=True, added=1, removed=1
)


def test_without_path_no_git_runs(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    witness = tmp_path / "witness"
    git = fake_git(tmp_path / "bin", f'touch "{witness}"\nexit 1')
    monkeypatch.setenv("PATH", f"{git.parent}:{os.environ['PATH']}")
    _ = launch_bash(ctx, env, BashLaunch(cwd=tmp_path), _ENVIRON)
    clock = _Clock()
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=clock)
    try:
        for _ in range(3):
            _ = backend.load()
            clock.now += 20
    finally:
        backend.close()
    assert not witness.exists()


def test_a_fresh_git_state_forces_a_reread(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    git_repo: GitRepo,
) -> None:
    (git_repo.path / "README.md").write_text("changed\n")
    _ = launch_bash(ctx, env, BashLaunch(cwd=git_repo.path), _ENVIRON)
    clock = _Clock()  # frozen: only a fresh Git state can make a load reread tmux
    poller = GitPoller(real_git(git_repo), git_repo.env, monotonic=clock)
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=clock, git=poller)
    try:
        first = backend.load()
        assert first is not None
        assert first.git == {}
        loaded: list[Mapping[Path, GitState]] = []

        def reread() -> bool:
            data = backend.load()
            if data is not None:
                loaded.append(data.git)
            return bool(loaded)

        wait_until("the git state", reread)
        assert loaded == [{git_repo.path: _CHANGED}]
        assert backend.load() is None  # the same state again: nothing changed
    finally:
        backend.close()


def test_close_closes_the_poller(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    pids = tmp_path / "pids"
    git = fake_git(tmp_path / "bin", f'echo $$ > "{pids}"\nexec sleep 30')
    _ = launch_bash(ctx, env, BashLaunch(cwd=tmp_path), _ENVIRON)
    backend = CliBoardBackend(ctx, env, _ENVIRON, git=GitPoller(git, {}))
    _ = backend.load()
    wait_until("git to start", lambda: pids.exists() and pids.read_text().strip() != "")
    sleeper = int(pids.read_text())
    backend.close()
    assert not Path(f"/proc/{sleeper}").exists()
