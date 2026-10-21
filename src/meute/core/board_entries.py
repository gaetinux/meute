"""What the board lets the user select: sessions, repositories and orphan panes."""

from dataclasses import dataclass

from meute.core.orphans import Orphan
from meute.core.repo import Repo
from meute.core.session import Session


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionRow:
    """A session with what tmux says about it."""

    session: Session
    has_pane: bool
    displayed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionEntry:
    """A selectable session."""

    row: SessionRow


@dataclass(frozen=True, slots=True, kw_only=True)
class RepoEntry:
    """A selectable repository."""

    repo: Repo


@dataclass(frozen=True, slots=True, kw_only=True)
class OrphanEntry:
    """A selectable orphan pane."""

    orphan: Orphan


LaunchEntry = SessionEntry | RepoEntry
"""The entries a launch, a stop or a resume can start from: not an orphan pane."""

BoardEntry = LaunchEntry | OrphanEntry
