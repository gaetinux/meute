"""The reconciliation rule between recorded sessions and observed tmux panes."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import Exited, Running, SessionState, Unreachable, is_live


@dataclass(frozen=True, slots=True, kw_only=True)
class PaneObservation:
    """A pane carrying `@meute_id`, as tmux reports it."""

    meute_id: str
    dead: bool
    exit_code: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Reconciliation:
    """The state changes to record and the pane identifiers matching no session."""

    updates: tuple[tuple[SessionId, SessionState], ...]
    orphans: tuple[str, ...]


def first_by_id[T](items: Iterable[T], key: Callable[[T], str | None]) -> dict[str, T]:
    """Map each identifier given by `key` to the first item carrying it, in order.

    Items whose `key` is None are ignored.
    """
    first: dict[str, T] = {}
    for item in items:
        meute_id = key(item)
        if meute_id is not None:
            first.setdefault(meute_id, item)
    return first


def _new_state(session: Session, pane: PaneObservation | None) -> SessionState | None:
    """Return the state `session` must take, or None when it stays as it is."""
    if pane is None:
        return Unreachable()
    if pane.dead:
        return Exited(code=pane.exit_code)
    if session.agent is AgentKind.BASH and session.state != Running():
        return Running()
    return None


def reconcile(sessions: Sequence[Session], panes: Sequence[PaneObservation]) -> Reconciliation:
    """Compare recorded sessions with observed panes (spec 5.4).

    Only live sessions are updated; ended ones are never resurrected. When several
    panes carry the same identifier, the first one counts.

    Args:
        sessions: The recorded sessions.
        panes: The panes carrying `@meute_id`, in tmux order.

    Returns:
        The updates, in session order, and the pane identifiers matching no session,
        without duplicates, in pane order.
    """
    by_id = first_by_id(panes, lambda pane: pane.meute_id)
    updates: list[tuple[SessionId, SessionState]] = []
    for session in sessions:
        if not is_live(session.state):
            continue
        new_state = _new_state(session, by_id.get(session.id))
        if new_state is not None:
            updates.append((session.id, new_state))
    known = {session.id for session in sessions}
    orphans = tuple(pane_id for pane_id in by_id if pane_id not in known)
    return Reconciliation(updates=tuple(updates), orphans=orphans)
