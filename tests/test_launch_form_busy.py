"""The busy folders of the launch form: refreshed on a reread, never raising on odd paths."""

from dataclasses import replace
from pathlib import Path

import pytest

from meute.core.board_view import SessionRow
from meute.core.launch_form import LaunchForm, open_form, shares_folder, with_busy
from support import BOARD_AT, BOARD_HOME, BOARD_SESSION_A, BOARD_SESSION_B, board_data


def _form() -> LaunchForm:
    return open_form(board_data(), None, default_mode="auto", now=BOARD_AT)


def test_with_busy_recomputes_only_the_busy_folders(tmp_path: Path) -> None:
    form = replace(_form(), folder="/typed", title="kept", error="kept too")
    session = replace(BOARD_SESSION_A, cwd=tmp_path)
    data = replace(
        board_data(), sessions=(SessionRow(session=session, has_pane=True, displayed=False),)
    )
    assert with_busy(form, data) == replace(form, busy=frozenset({tmp_path.resolve()}))


def test_a_folder_that_cannot_be_resolved_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_self: Path) -> Path:
        message = "too many levels of symbolic links"
        raise OSError(message)

    monkeypatch.setattr(Path, "resolve", fail)
    form = replace(_form(), folder="/strange", busy=frozenset({Path("/strange")}))
    assert shares_folder(form, BOARD_HOME)
    assert with_busy(form, board_data()).busy == frozenset(
        {BOARD_SESSION_A.cwd, BOARD_SESSION_B.cwd}
    )


def test_a_null_byte_in_the_folder_never_raises() -> None:
    assert not shares_folder(replace(_form(), folder="/a\x00b"), BOARD_HOME)
