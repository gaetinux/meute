"""Tests that kill mutants of the launch form, the orphan lines and the repository links."""

from dataclasses import replace
from pathlib import Path

from meute.core.board_sessions import board_sessions, line_entry
from meute.core.board_view import LaunchBash, OrphanEntry, RepoEntry
from meute.core.config_validate import PERMISSION_MODES
from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.repos import link_repo, repo_project_links, sync_repos
from meute.core.launch_form import (
    FormField,
    LaunchForm,
    choose,
    erase,
    form_action,
    move,
    open_form,
    type_text,
)
from meute.core.launch_form_view import (
    _choice,  # pyright: ignore[reportPrivateUsage] — no public caller reaches a width this small
    form_lines,
)
from meute.core.orphans import Orphan, orphan_line
from meute.core.repo import NewRepo
from meute.core.session import AgentKind
from meute.core.sessions_view import OrphanLine, ViewState, line_key
from meute.core.styled import Role, StyledLine, plain
from support import BOARD_AT, BOARD_HOME, BOARD_REPO_1, board_data

_NOW = BOARD_AT


def _form(**changes: object) -> LaunchForm:
    form = open_form(
        replace(board_data(), orphans=()),
        RepoEntry(repo=BOARD_REPO_1),
        default_mode="auto",
        now=_NOW,
    )
    return replace(form, **changes)


def test_an_unknown_default_mode_is_not_offered() -> None:
    form = open_form(board_data(), None, default_mode="bogus", now=_NOW)
    assert form.modes == tuple(sorted(PERMISSION_MODES))


def test_repositories_with_the_same_name_are_ordered_by_path() -> None:
    first = replace(BOARD_REPO_1, id=BOARD_REPO_1.id, path=Path("/a/same"), name="same")
    second = replace(BOARD_REPO_1, path=Path("/b/same"), name="same")
    data = replace(board_data(), repos=(second, first))
    form = open_form(data, None, default_mode="auto", now=_NOW)
    assert [repo.path for repo in form.repos] == [Path("/a/same"), Path("/b/same")]


def test_moving_from_a_field_the_type_hides_starts_at_the_first_field() -> None:
    form = _form(agent=AgentKind.BASH, field=FormField.TASK)
    assert move(form, 1).field is FormField.REPO
    assert move(form, -1).field is FormField.TITLE


def test_every_choice_and_edit_clears_the_error() -> None:
    data = replace(board_data(), orphans=())
    for field in (FormField.TASK, FormField.MODE, FormField.REPO):
        form = _form(field=field, error="boom", tasks=(), task=None)
        assert choose(form, 1, data, _NOW).error is None
    for field in (FormField.FOLDER, FormField.TITLE):
        form = _form(field=field, error="boom")
        assert type_text(form, "x").error is None
        assert erase(form).error is None
    assert choose(_form(field=FormField.REPO, repo=None, error="boom"), 1, data, _NOW).error is None
    assert choose(_form(field=FormField.REPO, error="boom"), -1, data, _NOW).error is None


def test_choosing_another_repository_forgets_the_task() -> None:
    data = replace(board_data(), orphans=())
    form = _form(field=FormField.REPO, task=0)
    assert choose(form, 1, data, _NOW).task is None


def test_erase_drops_only_the_last_character() -> None:
    assert erase(_form(field=FormField.FOLDER, folder="/abc")).folder == "/ab"
    assert erase(_form(field=FormField.TITLE, title="abc")).title == "ab"


def test_typed_text_keeps_one_space_at_each_edge() -> None:
    def typed(text: str) -> str:
        return type_text(_form(field=FormField.TITLE, title=""), text).title

    assert typed(" ab") == " ab"
    assert typed("ab ") == "ab "
    assert typed("a b") == "a b"
    assert typed("  ab  ") == " ab "
    assert typed("   ") == " "


def test_a_bash_launch_carries_its_title() -> None:
    form = _form(agent=AgentKind.BASH, title="  logs ", folder="/w")
    assert form_action(form, BOARD_HOME) == LaunchBash(
        cwd=Path("/w"), repo_id=BOARD_REPO_1.id, title="logs"
    )


def _lines(form: LaunchForm, width: int) -> list[StyledLine]:
    return form_lines(form, home=BOARD_HOME, width=width)


def test_a_row_without_room_keeps_its_whole_value_and_role() -> None:
    form = _form(field=FormField.MODE)
    for width in (10, 13, 14):  # room is negative, then zero
        row = _choice(form, FormField.MODE, "bypass", width, Role.RISKY)
        assert row[2].text == "bypass"
        assert row[2].role is Role.RISKY
    row = _choice(form, FormField.MODE, "bypass", 15, Role.RISKY)
    assert plain(row[2:-1]) == "…"


def test_the_current_field_label_is_titled_and_the_others_are_dim() -> None:
    lines = _lines(_form(field=FormField.TYPE), 72)
    assert lines[1][0].role is Role.TITLE
    assert lines[2][0].role is Role.DIM


def test_a_claude_form_without_a_task_says_none() -> None:
    lines = _lines(_form(task=None, tasks=()), 72)
    assert any(plain(line) == "Task      ◂ none ▸" for line in lines)


def test_a_folder_not_canonical_is_shown_as_typed() -> None:
    folder = f"{BOARD_HOME}/git/meute/"
    lines = _lines(_form(folder=folder), 72)
    assert any(plain(line) == f"Folder    {folder}" for line in lines)


def test_the_warning_expands_a_typed_home_and_is_a_warning() -> None:
    busy = frozenset({(BOARD_HOME / "git/meute").resolve()})
    lines = _lines(_form(folder="~/git/meute", busy=busy), 72)
    warning = [line for line in lines if plain(line).startswith("⚠")]
    assert [span.role for span in warning[0]] == [Role.WARN]


def test_an_orphan_line_says_command_folder_and_state() -> None:
    orphan = Orphan(meute_id="a", pane_id="%1", command="vim", cwd="", dead=False)
    assert orphan_line(orphan, BOARD_HOME) == "? vim    orphan"
    dead = replace(orphan, dead=True, cwd=str(BOARD_HOME / "x"))
    assert orphan_line(dead, BOARD_HOME) == "? vim  ~/x  dead"


def test_an_orphan_line_of_the_view_names_its_orphan() -> None:
    ghost = Orphan(meute_id="ghost", pane_id="%7", command="claude", cwd="/w", dead=False)
    other = replace(ghost, meute_id="other", pane_id="%8")
    board = board_sessions(replace(board_data(), orphans=(other, ghost)), ViewState())
    indexes = [i for i, line in enumerate(board.view.lines) if isinstance(line, OrphanLine)]
    assert [line_key(board.view.lines[i]) for i in indexes] == ["orphan:other", "orphan:ghost"]
    assert [line_entry(board, i) for i in indexes] == [
        OrphanEntry(orphan=other),
        OrphanEntry(orphan=ghost),
    ]


def test_an_orphan_line_without_its_orphan_gives_no_entry() -> None:
    ghost = Orphan(meute_id="ghost", pane_id="%7", command="claude", cwd="/w", dead=False)
    board = board_sessions(replace(board_data(), orphans=(ghost,)), ViewState())
    (index,) = [i for i, line in enumerate(board.view.lines) if isinstance(line, OrphanLine)]
    gone = replace(board, data=replace(board.data, orphans=()))
    assert line_entry(gone, index) is None


def test_repo_project_links_pair_each_repository_with_its_own_project(db: Database) -> None:
    one, two = sync_repos(
        db,
        [
            NewRepo(path=Path("/g/a"), name="a", kind=None),
            NewRepo(path=Path("/g/b"), name="b", kind=None),
        ],
    )
    create_project(db, "unused")
    create_project(db, "unused too")
    project = create_project(db, "p")
    link_repo(db, project.id, two.id)
    assert repo_project_links(db) == {two.id: project.id}
    assert one.id != project.id
