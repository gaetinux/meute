"""The non-blocking `claude agents --json` poller."""

import stat
import time
from pathlib import Path

from meute.claude.agents import run_agents
from meute.cli.agents_poller import AgentsPoller
from support import wait_until

_JSON = '[{"pid": 1, "cwd": "/w", "kind": "k", "sessionId": "s", "name": "n", "status": "idle"}]'


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _script(tmp_path: Path, body: str, name: str = "claude") -> Path:
    path = tmp_path / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _counting(tmp_path: Path, output: str = _JSON) -> tuple[Path, Path]:
    counter = tmp_path / "runs"
    script = _script(tmp_path, f"echo run >> {counter}\nprintf '%s' '{output}'")
    return script, counter


def _runs(counter: Path) -> int:
    return len(counter.read_text().splitlines()) if counter.exists() else 0


def _harvest(poller: AgentsPoller) -> object:
    found: list[object] = []

    def got() -> bool:
        result = poller.poll()
        if result is not None:
            found.append(result)
        return bool(found)

    wait_until("the poll result", got)
    return found[0]


def test_run_agents_returns_the_output(tmp_path: Path) -> None:
    script, _ = _counting(tmp_path)
    assert run_agents(script) == _JSON


def test_run_agents_failure_is_none(tmp_path: Path) -> None:
    assert run_agents(_script(tmp_path, "echo oops\nexit 3")) is None
    assert run_agents(tmp_path / "missing") is None


def test_run_agents_timeout_is_none(tmp_path: Path) -> None:
    started = time.monotonic()
    assert run_agents(_script(tmp_path, "sleep 30"), timeout=0.3) is None
    assert time.monotonic() - started < 5


def test_poll_launches_without_blocking_and_harvests(tmp_path: Path) -> None:
    script, counter = _counting(tmp_path)
    poller = AgentsPoller(script, monotonic=_Clock())
    result = _harvest(poller)
    assert isinstance(result, tuple)
    assert result[0].session_id == "s"  # pyright: ignore[reportUnknownMemberType] — narrowed by the test
    assert _runs(counter) == 1


def test_no_second_process_before_every(tmp_path: Path) -> None:
    script, counter = _counting(tmp_path)
    clock = _Clock()
    poller = AgentsPoller(script, every=10.0, monotonic=clock)
    _ = _harvest(poller)
    clock.now += 9.0
    assert poller.poll() is None
    time.sleep(0.3)
    assert poller.poll() is None
    assert _runs(counter) == 1
    clock.now += 1.5
    _ = poller.poll()
    wait_until("the second run", lambda: _runs(counter) == 2)


def test_slow_process_is_killed_after_five_seconds(tmp_path: Path) -> None:
    pidfile = tmp_path / "pid"
    script = _script(tmp_path, f"echo $$ > {pidfile}\nexec sleep 60")
    clock = _Clock()
    poller = AgentsPoller(script, every=10.0, monotonic=clock)
    assert poller.poll() is None
    wait_until("the process to start", lambda: pidfile.exists() and bool(pidfile.read_text()))
    pid = int(pidfile.read_text())
    clock.now += 4.0
    assert poller.poll() is None
    assert Path(f"/proc/{pid}").exists()
    clock.now += 1.5
    assert poller.poll() is None
    wait_until("the kill", lambda: not Path(f"/proc/{pid}").exists() or _zombie(pid))


def _zombie(pid: int) -> bool:
    try:
        return "Z" in Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return True


def test_failed_run_gives_nothing_then_retries(tmp_path: Path) -> None:
    script = _script(tmp_path, "exit 1")
    clock = _Clock()
    poller = AgentsPoller(script, monotonic=clock)
    for _ in range(3):
        assert poller.poll() is None
        time.sleep(0.2)
        clock.now += 11.0


def test_unreadable_output_is_an_empty_result(tmp_path: Path) -> None:
    script, _ = _counting(tmp_path, "garbage")
    assert _harvest(AgentsPoller(script, monotonic=_Clock())) == ()


def test_without_claude_poll_is_always_none() -> None:
    clock = _Clock()
    poller = AgentsPoller(None, monotonic=clock)
    for _ in range(3):
        assert poller.poll() is None
        clock.now += 20.0


def test_failed_flag_follows_the_last_harvest(tmp_path: Path) -> None:
    good, _ = _counting(tmp_path)
    clock = _Clock()
    poller = AgentsPoller(good, monotonic=clock)
    assert not poller.failed
    _ = _harvest(poller)
    assert not poller.failed
    bad = AgentsPoller(_script(tmp_path, "exit 1", "bad"), monotonic=clock)
    _ = bad.poll()
    wait_until("the failure", lambda: bad.poll() is None and bad.failed)
