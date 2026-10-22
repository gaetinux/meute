"""The lines of the Sessions view and how cards, groups and sections become them."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from meute.core.agents import AgentInfo
from meute.core.attention import needs_attention
from meute.core.orphans import Orphan
from meute.core.project import RepoId
from meute.core.repo import Repo
from meute.core.session import SessionId
from meute.core.session_state import is_live
from meute.core.sessions_view_bottom import (
    InfoLine,
    OrphanLine,
    RepoLine,
    SectionLine,
    TextLine,
    ViewState,
    bottom_blocks,
    is_folded_in,
    section_key,
)
from meute.core.sessions_view_text import (
    SessionInfo,
    card_first_line,
    card_more_lines,
    dim_line,
    header_line,
    needs_you_first_line,
    needs_you_heading,
    ref_line,
)
from meute.core.styled import Role, StyledLine, title_rule

OTHER_GROUP = "Other"
NOTHING_TO_SHOW = "Nothing needs your attention."
NEEDS_YOU = "Needs you"


@dataclass(frozen=True, slots=True, kw_only=True)
class HeaderLine(TextLine):
    """The header of a group; `repo_id` is the repository of its first session, if known."""

    group: str
    spans: StyledLine
    collapsed: bool = False
    repo_id: RepoId | None = None
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionLine(TextLine):
    """A selectable session: the first line of its card."""

    session_id: SessionId
    spans: StyledLine
    attention: bool
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class CardLine(TextLine):
    """Line 2 or 3 of a session's card; not selectable, a click selects its session."""

    session_id: SessionId
    spans: StyledLine
    band: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RefLine(TextLine):
    """Where a session shown in "Needs you" sits in its group; not selectable."""

    session_id: SessionId
    spans: StyledLine
    band: bool = False


ViewLine = (
    HeaderLine | SessionLine | CardLine | RefLine | SectionLine | RepoLine | OrphanLine | InfoLine
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionsView:
    """The lines of the Sessions view, top to bottom."""

    lines: tuple[ViewLine, ...]


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
    folded = is_folded_in(state, section_key(NEEDS_YOU))
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


def build_view(  # noqa: PLR0913 — everything the view draws, the clock, home and width
    infos: Sequence[SessionInfo],
    repos: Sequence[Repo],
    outside: Sequence[AgentInfo],
    orphans: Sequence[Orphan | str],
    state: ViewState,
    *,
    now: datetime,
    home: Path | None,
    width: int,
) -> SessionsView:
    """Build the lines of the Sessions view, `width` columns at most, from the data and choices.

    Sessions waiting for the user come first in "Needs you" (except with `attention_only`,
    where each stays in its group), then the groups, a blank line between these blocks; then
    a dim rule, when something is above it, and the bottom sections one under the other.
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
    lines: list[ViewLine] = []
    for block in blocks:
        lines += [InfoLine(spans=()), *block] if lines else block
    bottom = bottom_blocks(
        infos, repos, outside=outside, orphans=orphans, state=state, home=home, width=width
    )
    if lines and bottom:
        lines.append(InfoLine(spans=title_rule(None, width, Role.DIM)))
    for block in bottom:
        lines += block
    return SessionsView(lines=tuple(lines))
