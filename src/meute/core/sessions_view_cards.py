"""The lines of the Sessions view and how cards, groups and sections become them."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from meute.core.agents import AgentInfo
from meute.core.attention import needs_attention
from meute.core.board_view import ORPHANS_HEADING, OUTSIDE_HEADING, outside_line
from meute.core.board_view import repo_line as _board_repo_line
from meute.core.project import RepoId
from meute.core.repo import Repo
from meute.core.session import SessionId
from meute.core.session_state import is_live
from meute.core.sessions_view_text import (
    SessionInfo,
    card_first_line,
    card_more_lines,
    dim_line,
    header_line,
    item_line,
    needs_you_first_line,
    needs_you_heading,
    ref_line,
    section_line,
)
from meute.core.styled import StyledLine, plain
from meute.core.text import printable

OTHER_GROUP = "Other"
NOTHING_TO_SHOW = "Nothing needs your attention."
NEEDS_YOU = "Needs you"
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


class _Line:
    """What every view line has: its styled segments, whose text is `text`."""

    __slots__ = ()
    spans: StyledLine

    @property
    def text(self) -> str:
        """The text of the line without its roles."""
        return plain(self.spans)


@dataclass(frozen=True, slots=True, kw_only=True)
class HeaderLine(_Line):
    """The header of a group; `repo_id` is the repository of its first session, if known."""

    group: str
    spans: StyledLine
    collapsed: bool = False
    repo_id: RepoId | None = None
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionLine(_Line):
    """A selectable session: the first line of its card."""

    session_id: SessionId
    spans: StyledLine
    attention: bool
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class CardLine(_Line):
    """Line 2 or 3 of a session's card; not selectable, a click selects its session."""

    session_id: SessionId
    spans: StyledLine
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RefLine(_Line):
    """Where a session shown in "Needs you" sits in its group; not selectable."""

    session_id: SessionId
    spans: StyledLine
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class SectionLine(_Line):
    """The heading of a section ("Needs you" or a bottom one); selectable when folded."""

    section: str
    spans: StyledLine
    collapsed: bool = False
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RepoLine(_Line):
    """A selectable repository without a live session."""

    repo_id: RepoId
    spans: StyledLine
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class InfoLine(_Line):
    """A line that cannot be selected."""

    spans: StyledLine
    band: bool = False


ViewLine = HeaderLine | SessionLine | CardLine | RefLine | SectionLine | RepoLine | InfoLine


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionsView:
    """The lines of the Sessions view, top to bottom."""

    lines: tuple[ViewLine, ...]


def section_key(section: str) -> str:
    """Return the key that folds `section` in `ViewState`, apart from the group names."""
    return f"section:{section}"


def _folded(state: ViewState, key: str, *, default: bool = False) -> bool:
    return key in state.collapsed or (default and key not in state.expanded)


def _group_order(name: str) -> tuple[bool, str, str]:
    return (name == OTHER_GROUP, name.casefold(), name)


def _card(info: SessionInfo, first: StyledLine, width: int, *, band: bool) -> list[ViewLine]:
    session_id = info.row.session.id
    attention = needs_attention(info.row.session.state)
    lines: list[ViewLine] = [
        SessionLine(session_id=session_id, spans=first, attention=attention, band=band)
    ]
    more = card_more_lines(info, width=width)
    return lines + [CardLine(session_id=session_id, spans=s, band=band) for s in more]


def _needs_you(urgent: Sequence[SessionInfo], state: ViewState, width: int) -> list[ViewLine]:
    folded = _folded(state, section_key(NEEDS_YOU))
    heading = needs_you_heading(NEEDS_YOU, len(urgent), folded=folded)
    lines: list[ViewLine] = [SectionLine(section=NEEDS_YOU, spans=heading, collapsed=folded)]
    if not folded:
        for info in urgent:
            lines += _card(info, needs_you_first_line(info, width=width), width, band=True)
    return lines


def _group_lines(  # noqa: PLR0913 — the group, its repository, the user's choices, the clock
    group: str,
    *,
    members: Sequence[SessionInfo],
    repos: Mapping[RepoId, Repo],
    state: ViewState,
    now: datetime,
    width: int,
) -> list[ViewLine]:
    folded = group in state.collapsed
    repo_id = next((r for i in members if (r := i.row.session.repo_id) is not None), None)
    repo = repos.get(repo_id) if repo_id is not None else None
    spans = header_line(
        group,
        members,
        kind=None if repo is None else repo.kind,
        button=repo_id is not None,
        folded=folded,
        width=width,
    )
    lines: list[ViewLine] = [
        HeaderLine(group=group, spans=spans, collapsed=folded, repo_id=repo_id)
    ]
    if folded:
        return lines
    ended = 0
    for info in members:
        session = info.row.session
        attention = needs_attention(session.state)
        if state.attention_only and not attention:
            continue
        if not is_live(session.state) and not state.show_ended:
            ended += 1
        elif attention and not state.attention_only:
            lines.append(RefLine(session_id=session.id, spans=ref_line(info, width=width)))
        else:
            lines += _card(info, card_first_line(info, now=now, width=width), width, band=False)
    if ended and not state.attention_only:
        lines.append(InfoLine(spans=dim_line(f"  + {ended} ended (e to show)", width)))
    return lines


def _section(
    title: str, items: Sequence[ViewLine], state: ViewState, *, default: bool = False
) -> list[ViewLine]:
    folded = _folded(state, section_key(title), default=default)
    heading = section_line(title, len(items), folded=folded)
    return [SectionLine(section=title, spans=heading, collapsed=folded), *([] if folded else items)]


def _bottom_blocks(  # noqa: PLR0913 — what the bottom sections list, the user's choices, width
    infos: Sequence[SessionInfo],
    repos: Sequence[Repo],
    *,
    outside: Sequence[AgentInfo],
    orphans: Sequence[str],
    state: ViewState,
    home: Path | None,
    width: int,
) -> list[list[ViewLine]]:
    busy = {i.row.session.repo_id for i in infos if is_live(i.row.session.state)}
    idle = [
        RepoLine(repo_id=r.id, spans=item_line(_board_repo_line(r), width))
        for r in repos
        if r.id not in busy
    ]
    agents = [InfoLine(spans=item_line(outside_line(a, home), width)) for a in outside]
    panes = [InfoLine(spans=item_line(printable(o), width)) for o in orphans]
    blocks: list[list[ViewLine]] = []
    if idle:
        folded = len(idle) > REPOS_FOLDED_ABOVE
        blocks.append(_section(WITHOUT_SESSION, idle, state, default=folded))
    if agents:
        blocks.append(_section(OUTSIDE_HEADING, agents, state))
    if panes:
        blocks.append(_section(ORPHANS_HEADING, panes, state))
    return blocks


def build_view(  # noqa: PLR0913 — everything the view draws, the clock, home and width
    infos: Sequence[SessionInfo],
    repos: Sequence[Repo],
    outside: Sequence[AgentInfo],
    orphans: Sequence[str],
    state: ViewState,
    *,
    now: datetime,
    home: Path | None,
    width: int,
) -> SessionsView:
    """Build the lines of the Sessions view, `width` columns at most, from the data and choices.

    Sessions waiting for the user come first in "Needs you" (except with `attention_only`,
    where each stays in its group), then the groups, then the bottom sections; a blank line
    separates the blocks.
    """
    groups: dict[str, list[SessionInfo]] = {}
    for info in infos:
        groups.setdefault(info.group, []).append(info)
    order = sorted(groups, key=_group_order)
    by_id = {repo.id: repo for repo in repos}
    blocks: list[list[ViewLine]] = []
    urgent = [i for g in order for i in groups[g] if needs_attention(i.row.session.state)]
    if urgent and not state.attention_only:
        blocks.append(_needs_you(urgent, state, width))
    for group in order:
        members = groups[group]
        if state.attention_only and not any(needs_attention(i.row.session.state) for i in members):
            continue
        blocks.append(
            _group_lines(group, members=members, repos=by_id, state=state, now=now, width=width)
        )
    if state.attention_only and not blocks:
        blocks.append([InfoLine(spans=dim_line(NOTHING_TO_SHOW, width))])
    blocks += _bottom_blocks(
        infos, repos, outside=outside, orphans=orphans, state=state, home=home, width=width
    )
    lines: list[ViewLine] = []
    for block in blocks:
        lines += [InfoLine(spans=()), *block] if lines else block
    return SessionsView(lines=tuple(lines))
