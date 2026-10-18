import pytest

from meute.tmux.errors import UnreadableOutput
from meute.tmux.parse import PaneId, PaneInfo, parse_pane_line


def test_parse_dead_pane() -> None:
    pane = parse_pane_line("%3\tmeute-bg\tw\t0b9f\t\t1\t7\t80")
    assert pane == PaneInfo(
        id=PaneId("%3"),
        session="meute-bg",
        window="w",
        meute_id="0b9f",
        role=None,
        dead=True,
        dead_status=7,
        width=80,
    )


def test_parse_live_pane_with_role() -> None:
    pane = parse_pane_line("%4\tmeute\tmain\t\tboard\t0\t\t120")
    assert not pane.dead
    assert pane.dead_status is None
    assert pane.meute_id is None
    assert pane.role == "board"
    assert pane.width == 120


def test_seven_fields_are_unreadable() -> None:
    with pytest.raises(UnreadableOutput):
        parse_pane_line("%3\tmeute-bg\tw\tid\t\t1\t7")


def test_nine_fields_are_unreadable() -> None:
    with pytest.raises(UnreadableOutput):
        parse_pane_line("%3\tmeute-bg\tw\tid\t\t1\t7\t80\textra")


def test_non_numeric_width_is_unreadable() -> None:
    with pytest.raises(UnreadableOutput):
        parse_pane_line("%3\tmeute-bg\tw\tid\t\t1\t7\twide")


def test_non_numeric_status_is_unreadable() -> None:
    with pytest.raises(UnreadableOutput):
        parse_pane_line("%3\tmeute-bg\tw\tid\t\t1\tseven\t80")
