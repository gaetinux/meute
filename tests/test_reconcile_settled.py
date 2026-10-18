"""A dead pane whose exit is not settled yet is not reconciled."""

from pathlib import Path

from meute.core.reconcile import PaneObservation, reconcile
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import Exited, Running
from support import FIXED

A = SessionId("00000000-0000-4000-8000-00000000000a")


def session() -> Session:
    return Session(
        id=A,
        agent=AgentKind.CLAUDE,
        title="t",
        project_id=None,
        repo_id=None,
        task_id=None,
        cwd=Path("/srv"),
        state=Running(),
        last_activity_at=FIXED,
        created_at=FIXED,
        ended_at=None,
    )


def test_unsettled_dead_pane_is_not_reconciled_yet() -> None:
    pane = PaneObservation(meute_id=A, dead=True, exit_code=None, settled=False)
    assert reconcile([session()], [pane]).updates == ()


def test_settled_dead_pane_is_reconciled() -> None:
    pane = PaneObservation(meute_id=A, dead=True, exit_code=None)
    assert reconcile([session()], [pane]).updates == ((A, Exited(code=None)),)
