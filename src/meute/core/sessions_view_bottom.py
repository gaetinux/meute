"""The Sessions view's bottom sections, and the line types and fold state they share."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from meute.core.agents import AgentInfo
from meute.core.board_view import ORPHANS_HEADING, OUTSIDE_HEADING, outside_line
from meute.core.board_view import repo_line as _board_repo_line
from meute.core.orphans import Orphan, orphan_line
from meute.core.project import RepoId
from meute.core.repo import Repo
from meute.core.session_state import is_live
from meute.core.sessions_view_text import SessionInfo, item_line, section_line
from meute.core.styled import StyledLine, plain
from meute.core.text import printable

WITHOUT_SESSION = "Without session"
REPOS_FOLDED_ABOVE = 5
""""Without session" starts folded when it holds more repositories than this."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ViewState:
    """What the user chose to fold, filter and reveal.

    `collapsed` holds the folded groups and sections (by `fold_key`); `expanded` the sections
    the user unfolded although they start folded.
    """

    collapsed: frozenset[str] = frozenset()
    expanded: frozenset[str] = frozenset()
    attention_only: bool = False
    show_ended: bool = False


class TextLine:
    """What every view line has: its styled segments, whose text is `text`."""

    __slots__ = ()
    spans: StyledLine

    @property
    def text(self) -> str:
        """The text of the line without its roles."""
        return plain(self.spans)


@dataclass(frozen=True, slots=True, kw_only=True)
class SectionLine(TextLine):
    """The heading of a section ("Needs you" or a bottom one); selectable when folded."""

    section: str
    spans: StyledLine
    collapsed: bool = False
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RepoLine(TextLine):
    """A selectable repository without a live session."""

    repo_id: RepoId
    spans: StyledLine
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class OrphanLine(TextLine):
    """A selectable orphan pane, identified by its `@meute_id`."""

    meute_id: str
    spans: StyledLine
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class InfoLine(TextLine):
    """A line that cannot be selected."""

    spans: StyledLine
    band: bool = False


def section_key(section: str) -> str:
    """Return the key that folds `section` in `ViewState`, apart from the group names."""
    return f"section:{section}"


def is_folded_in(state: ViewState, key: str, *, default: bool = False) -> bool:
    """Return whether `key` is folded: chosen so, or by `default` unless the user unfolded it."""
    return key in state.collapsed or (default and key not in state.expanded)


def _section(
    title: str,
    items: Sequence[RepoLine | OrphanLine | InfoLine],
    state: ViewState,
    *,
    default: bool = False,
) -> list[SectionLine | RepoLine | OrphanLine | InfoLine]:
    folded = is_folded_in(state, section_key(title), default=default)
    heading = section_line(title, len(items), folded=folded)
    return [SectionLine(section=title, spans=heading, collapsed=folded), *([] if folded else items)]


def _orphan_item(item: Orphan | str, home: Path | None, width: int) -> OrphanLine | InfoLine:
    if isinstance(item, str):  # a bare identifier: no pane to act on
        return InfoLine(spans=item_line(printable(item), width))
    return OrphanLine(meute_id=item.meute_id, spans=item_line(orphan_line(item, home), width))


def bottom_blocks(  # noqa: PLR0913 — what the bottom sections list, the user's choices, width
    infos: Sequence[SessionInfo],
    repos: Sequence[Repo],
    *,
    outside: Sequence[AgentInfo],
    orphans: Sequence[Orphan | str],
    state: ViewState,
    home: Path | None,
    width: int,
) -> list[list[SectionLine | RepoLine | OrphanLine | InfoLine]]:
    """Return the sections under the groups: repositories without a session, outside, orphans.

    An `Orphan` gives a selectable line; a bare identifier (`str`) an information line.
    """
    busy = {i.row.session.repo_id for i in infos if is_live(i.row.session.state)}
    idle = [
        RepoLine(repo_id=r.id, spans=item_line(_board_repo_line(r), width))
        for r in repos
        if r.id not in busy
    ]
    agents = [InfoLine(spans=item_line(outside_line(a, home), width)) for a in outside]
    panes = [_orphan_item(o, home, width) for o in orphans]
    blocks: list[list[SectionLine | RepoLine | OrphanLine | InfoLine]] = []
    if idle:
        folded = len(idle) > REPOS_FOLDED_ABOVE
        blocks.append(_section(WITHOUT_SESSION, idle, state, default=folded))
    if agents:
        blocks.append(_section(OUTSIDE_HEADING, agents, state))
    if panes:
        blocks.append(_section(ORPHANS_HEADING, panes, state))
    return blocks
