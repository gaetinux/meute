"""Polling `claude agents --json` from the dashboard without ever waiting for it."""

import time
from collections.abc import Callable
from pathlib import Path

from meute.claude.agents import AgentsRun, finish_agents, kill_agents, start_agents
from meute.core.agents import AgentInfo, parse_agents

KILL_AFTER_SECONDS = 5.0


class AgentsPoller:
    """Starts the command at most every `every` seconds and harvests it when it is done."""

    def __init__(
        self,
        claude: Path | None,
        *,
        every: float = 10.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._claude = claude
        self._every = every
        self._monotonic = monotonic
        self._run: AgentsRun | None = None
        self._started_at: float | None = None
        self._failed = False

    @property
    def failed(self) -> bool:
        """Whether the last run failed, timed out or could not start."""
        return self._failed

    def poll(self) -> tuple[AgentInfo, ...] | None:
        """Return a fresh result, or `None` while there is nothing new; never blocks."""
        now = self._monotonic()
        result = self._harvest(now)
        if (
            self._claude is not None
            and self._run is None
            and (self._started_at is None or now - self._started_at >= self._every)
        ):
            self._started_at = now
            self._run = start_agents(self._claude)
            if self._run is None:
                self._failed = True
        return result

    def close(self) -> None:
        """Kill the command still running, if any."""
        if self._run is not None:
            kill_agents(self._run)
            self._run = None

    def _harvest(self, now: float) -> tuple[AgentInfo, ...] | None:
        run = self._run
        if run is None or self._started_at is None:
            return None
        if run.process.poll() is not None:
            self._run = None
            text = finish_agents(run)
            self._failed = text is None
            return None if text is None else parse_agents(text)
        if now - self._started_at > KILL_AFTER_SECONDS:
            self._run = None
            self._failed = True
            kill_agents(run)
        return None
