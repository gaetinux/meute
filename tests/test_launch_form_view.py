"""Tests for the launch form lines."""

from dataclasses import replace
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from meute.core.board_view import RepoEntry
from meute.core.launch_form import FormField, LaunchForm, open_form
from meute.core.launch_form_view import form_lines
from meute.core.launch_form_worktree import NoWorktree
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.session import AgentKind
from meute.core.styled import Role, StyledLine, plain
from support import BOARD_AT, BOARD_HOME, BOARD_REPO_1, board_data, make_task


def _form() -> LaunchForm:
    project = ProjectRef(id=ProjectId(7), name="meute")
    task = replace(make_task(12), title="Fix the bug", project=project)
    data = replace(board_data(), tasks=(task,), repo_projects={RepoId(1): project.id})
    form = open_form(data, RepoEntry(repo=BOARD_REPO_1), default_mode="auto", now=BOARD_AT)
    return replace(form, task=0, worktree=NoWorktree())


def _texts(lines: list[StyledLine]) -> list[str]:
    return [plain(line) for line in lines]


def test_claude_form_with_warning(snapshot: SnapshotAssertion) -> None:
    form = replace(_form(), busy=frozenset({BOARD_REPO_1.path.resolve()}))
    assert _texts(form_lines(form, home=BOARD_HOME, width=72)) == snapshot


def test_bash_form_hides_task_and_mode(snapshot: SnapshotAssertion) -> None:
    form = replace(_form(), agent=AgentKind.BASH, field=FormField.FOLDER)
    assert _texts(form_lines(form, home=BOARD_HOME, width=72)) == snapshot


def test_error_form(snapshot: SnapshotAssertion) -> None:
    form = replace(_form(), error="folder not found: /n'existe/pas\x1b[2J", repo=None)
    assert _texts(form_lines(form, home=BOARD_HOME, width=72)) == snapshot


@pytest.mark.parametrize("width", [60, 30, 14, 5, 1])
def test_no_line_overflows_a_narrow_width(width: int, snapshot: SnapshotAssertion) -> None:
    project = ProjectRef(id=ProjectId(7), name="meute")
    task = replace(make_task(12), title="An extremely long task title " * 4, project=project)
    base = _form()
    form = replace(
        base,
        tasks=(task,),
        title="a very long title " * 5,
        error="something went wrong " * 5,
        busy=frozenset({BOARD_REPO_1.path.resolve()}),
        folder=str(Path("/home/me/git/meute")),
    )
    lines = form_lines(form, home=BOARD_HOME, width=width)
    assert all(len(plain(line)) <= width for line in lines)
    if width == 60:
        assert _texts(lines) == snapshot


def test_roles() -> None:
    form = replace(_form(), field=FormField.TITLE, error="boom")
    lines = form_lines(replace(form, mode=1), home=BOARD_HOME, width=72)
    assert lines[0][0].role is Role.ACCENT
    rows = {plain(line)[:10].strip(): line for line in lines}
    assert rows["Title"][0].role is Role.TITLE
    assert rows["Type"][0].role is Role.DIM
    assert lines[-2][0].role is Role.HIGH
    assert lines[-1][0].role is Role.DIM


def test_risky_mode_uses_the_risky_role() -> None:
    form = _form()
    index = form.modes.index("bypassPermissions")
    lines = form_lines(replace(form, mode=index), home=BOARD_HOME, width=72)
    mode = next(line for line in lines if plain(line).startswith("Mode"))
    assert any(span.role is Role.RISKY and "bypassPermissions" in span.text for span in mode)
    calm = form_lines(replace(form, mode=form.modes.index("plan")), home=BOARD_HOME, width=72)
    calm_mode = next(line for line in calm if plain(line).startswith("Mode"))
    assert all(span.role is not Role.RISKY for span in calm_mode)


def test_hostile_text_is_neutralised() -> None:
    form = replace(_form(), title="a\x1b[31mb", folder="/x\x07y")
    text = "\n".join(_texts(form_lines(form, home=BOARD_HOME, width=72)))
    assert "\x1b" not in text
    assert "\x07" not in text
