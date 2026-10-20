"""The rules and blank lines of the Sessions view, as in mockup C2."""

from meute.core.agents import AgentInfo
from meute.core.project import RepoId
from meute.core.session_state import Idle, PermissionRequested, Running
from meute.core.sessions_view import InfoLine, SectionLine, line_key
from meute.core.styled import Role, Span
from support import board_repo
from test_sessions_cards import (
    _WIDTH,  # pyright: ignore[reportPrivateUsage] — view test helper
    _info,  # pyright: ignore[reportPrivateUsage] — view test helper
    _texts,  # pyright: ignore[reportPrivateUsage] — view test helper
    _view,  # pyright: ignore[reportPrivateUsage] — view test helper
)

_RULE = "─" * _WIDTH
_OUTSIDE = AgentInfo(pid=4, cwd="/home/me/w", kind="cli", session_id="s", name="ext", status="busy")


def test_blank_lines_between_top_blocks_then_a_rule_above_the_bottom_sections() -> None:
    infos = [
        _info(1, "ask", PermissionRequested(), group="alpha"),
        _info(2, "calm", Running(), group="beta", repo_id=RepoId(1)),
    ]
    repos = [board_repo(1, "beta", None), board_repo(2, "notes", None)]
    texts = _texts(_view(infos, repos=repos, outside=[_OUTSIDE], orphans=["%7"]))
    beta = next(t for t in texts if t.startswith("▼ beta"))
    assert texts == [
        "Needs you (1)",
        "  ! ask · alpha · permission requested",
        "",
        "▼ alpha · 1 live",
        "  ! ask  ↑ needs you",
        "",
        beta,
        "  ● calm  running  5m ago",
        _RULE,
        "▼ Without session (1)",
        "  notes",
        "▼ Outside meute (1)",
        "  ext  busy  ~/w",
        "▼ Orphans (1)",
        "  %7",
    ]


def test_the_rule_is_a_dim_line_that_cannot_be_selected() -> None:
    view = _view([_info(1, "calm", Idle())], repos=[board_repo(2, "notes", None)])
    rule = view.lines[2]
    assert rule == InfoLine(spans=(Span(_RULE, Role.DIM),))
    assert line_key(rule) is None
    assert isinstance(view.lines[3], SectionLine)


def test_no_rule_without_anything_above_the_bottom_sections() -> None:
    texts = _texts(_view([], repos=[board_repo(2, "notes", None)], orphans=["%7"]))
    assert texts == ["▼ Without session (1)", "  notes", "▼ Orphans (1)", "  %7"]


def test_no_rule_without_bottom_sections() -> None:
    texts = _texts(_view([_info(1, "calm", Idle())]))
    assert texts == ["▼ alpha · 1 live", "  ○ calm  idle  5m ago"]
