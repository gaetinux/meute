"""The displayed mark of a card, the width guard and folding "Needs you" from its card."""

from dataclasses import replace
from datetime import timedelta

from meute.core.board_sessions import board_sessions
from meute.core.board_view import BoardData, SessionRow
from meute.core.session import SessionId
from meute.core.session_state import Running, WaitingInput
from meute.core.sessions_view import SessionLine, ViewState
from meute.core.sessions_view_text import dim_line, item_line
from meute.core.styled import Role, plain
from meute.tui.sessions_cursor import SessionsCursor
from support import BOARD_AT, BOARD_HOME, board_session

_ID_A = SessionId("00000001-1111-4111-8111-111111111111")
_ID_B = SessionId("00000002-1111-4111-8111-111111111111")


def _data(*, displayed: SessionId | None) -> BoardData:
    rows: list[SessionRow] = []
    for session_id, title, state in (
        (_ID_A, "build", Running()),
        (_ID_B, "review", WaitingInput()),
    ):
        base = board_session(session_id, title, BOARD_HOME / "git" / title, None, exited=False)
        session = replace(base, state=state, last_activity_at=BOARD_AT)
        rows.append(SessionRow(session=session, has_pane=True, displayed=session_id == displayed))
    return BoardData(
        sessions=tuple(rows),
        repos=(),
        orphans=(),
        home=BOARD_HOME,
        now=BOARD_AT + timedelta(minutes=5),
    )


def _first_lines(data: BoardData) -> dict[SessionId, SessionLine]:
    lines = board_sessions(data, ViewState()).view.lines
    return {line.session_id: line for line in lines if isinstance(line, SessionLine)}


def test_the_displayed_session_gets_an_accent_mark_in_column_zero() -> None:
    plain_card = _first_lines(_data(displayed=None))[_ID_A]
    shown = _first_lines(_data(displayed=_ID_A))[_ID_A]
    assert plain_card.text.startswith("  ● ")
    assert shown.text.startswith("▶ ● ")
    assert [s.role for s in shown.spans if s.text == "▶"] == [Role.ACCENT]


def test_the_displayed_mark_also_shows_in_needs_you() -> None:
    lines = board_sessions(_data(displayed=_ID_B), ViewState()).view.lines
    cards = [line for line in lines if isinstance(line, SessionLine) and line.band]
    assert [c.text[:4] for c in cards] == ["▶ ! "]
    refs = [line.text for line in lines if "needs you" in line.text and "↑" in line.text]
    assert refs
    assert not refs[0].startswith("▶")


def test_space_on_a_needs_you_card_folds_the_section_not_the_project() -> None:
    cursor = SessionsCursor()
    cursor.rebuild(_data(displayed=None))
    cursor.selected = next(
        i
        for i, line in enumerate(cursor.model.view.lines)
        if isinstance(line, SessionLine) and line.band
    )
    assert cursor.handle_key("space")
    texts = [line.text for line in cursor.model.view.lines]
    assert any(t.startswith("▶ Needs you (1)") for t in texts)
    assert any("build" in t for t in texts)  # the project group is still open
    assert cursor.model.view.lines[cursor.selected].text.startswith("▶ Needs you")
    assert cursor.handle_key("right")
    assert not any(
        t.startswith("▶ Needs you") for t in [line.text for line in cursor.model.view.lines]
    )


def test_a_zero_width_gives_empty_lines() -> None:
    assert item_line("anything", 0) == ()
    assert plain(dim_line("anything", -3)) == ""
