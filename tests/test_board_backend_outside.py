"""The backend shows the sessions outside meute found by its poller."""

from meute.cli.agents_poller import AgentsPoller
from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.tmux_env import TmuxEnv
from meute.core.agents import AgentInfo
from test_board_backend import _Clock, _loaded, ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportPrivateUsage, reportUnusedImport] — fixtures reused

_AGENT = AgentInfo(pid=1, cwd="/w", kind="i", session_id="x", name="n", status="busy")


class _Scripted(AgentsPoller):
    def __init__(self, results: list[tuple[AgentInfo, ...] | None]) -> None:
        super().__init__(None)
        self._results = results

    def poll(self) -> tuple[AgentInfo, ...] | None:
        return self._results.pop(0) if self._results else None


def test_new_poll_result_forces_a_reload_and_is_remembered(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    clock = _Clock()
    backend = CliBoardBackend(ctx, env, {}, monotonic=clock, agents=_Scripted([None, (_AGENT,)]))
    assert _loaded(backend).outside == ()
    assert backend.load() is not None  # the poller delivered: reread at once
    clock.now += 2.5
    assert _loaded(backend).outside == (_AGENT,)  # remembered until the next result


def test_no_claude_in_environ_means_no_poller(ctx: CliContext, env: TmuxEnv) -> None:  # noqa: F811 — fixture
    backend = CliBoardBackend(ctx, env, {}, monotonic=_Clock())
    assert _loaded(backend).outside == ()
