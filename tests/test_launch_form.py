"""Tests for the launch form state."""

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from meute.core.board_view import (
    BoardData,
    BoardEntry,
    LaunchBash,
    LaunchClaude,
    OrphanEntry,
    RepoEntry,
    SessionEntry,
    SessionRow,
)
from meute.core.config_validate import PERMISSION_MODES
from meute.core.launch_form import (
    FormField,
    LaunchForm,
    choose,
    erase,
    form_action,
    move,
    open_form,
    shares_folder,
    type_text,
)
from meute.core.launch_form_worktree import NoWorktree
from meute.core.orphans import Orphan
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.session import AgentKind
from meute.core.status import Done, TaskStatus
from meute.core.task import Due, DueDate, Task, TaskId
from support import (
    BOARD_AT,
    BOARD_HOME,
    BOARD_REPO_1,
    BOARD_REPO_2,
    BOARD_SESSION_A,
    board_data,
    make_task,
)

_NOW = BOARD_AT
_PROJECT = ProjectRef(id=ProjectId(7), name="meute")


def _task(
    task_id: int,
    *,
    project: ProjectRef | None = _PROJECT,
    due: Due | None = None,
    status: TaskStatus | None = None,
    completed_at: datetime | None = None,
) -> Task:
    task = make_task(task_id, due=due, status=status, completed_at=completed_at)
    return replace(task, project=project)


def _data() -> BoardData:
    tasks = (
        _task(1, due=DueDate(day=(_NOW + timedelta(days=3)).date())),
        _task(2, due=DueDate(day=(_NOW - timedelta(days=1)).date())),
        _task(3, status=Done(), completed_at=_NOW),
        _task(4, project=None),
        _task(5, project=ProjectRef(id=ProjectId(8), name="other")),
    )
    return replace(board_data(), tasks=tasks, repo_projects={RepoId(1): _PROJECT.id})


def _form(entry: BoardEntry | None = None) -> LaunchForm:
    return open_form(_data(), entry, default_mode="auto", now=_NOW)


def test_open_on_a_repo_prefills_it() -> None:
    form = open_form(_data(), RepoEntry(repo=BOARD_REPO_2), default_mode="auto", now=_NOW)
    assert form.agent is AgentKind.CLAUDE
    assert [repo.name for repo in form.repos] == ["notes", "meute"]
    assert form.repo == 0
    assert form.folder == str(BOARD_REPO_2.path)
    assert form.title == ""
    assert form.tasks == ()
    assert form.task is None
    assert form.field is FormField.TYPE
    assert form.error is None


def test_open_on_a_repo_proposes_the_open_tasks_of_its_project_by_urgency() -> None:
    form = open_form(_data(), RepoEntry(repo=BOARD_REPO_1), default_mode="auto", now=_NOW)
    assert [task.id for task in form.tasks] == [2, 1]


def test_open_on_a_session_prefills_its_folder_repo_task_and_type() -> None:
    session = replace(BOARD_SESSION_A, repo_id=RepoId(1), task_id=TaskId(1))
    entry = SessionEntry(row=SessionRow(session=session, has_pane=True, displayed=False))
    data = replace(_data(), last_agents={RepoId(1): AgentKind.BASH})
    form = open_form(data, entry, default_mode="auto", now=_NOW)
    assert form.agent is AgentKind.BASH
    assert form.repos[0] == BOARD_REPO_1
    assert form.folder == str(session.cwd)
    assert form.task == 1


def test_open_on_a_session_with_a_task_outside_the_project_has_no_task() -> None:
    session = replace(BOARD_SESSION_A, repo_id=RepoId(1), task_id=TaskId(5))
    entry = SessionEntry(row=SessionRow(session=session, has_pane=True, displayed=False))
    assert open_form(_data(), entry, default_mode="auto", now=_NOW).task is None


def test_open_on_a_session_without_repo_selects_none_but_keeps_its_folder() -> None:
    entry = SessionEntry(row=SessionRow(session=BOARD_SESSION_A, has_pane=True, displayed=False))
    form = open_form(_data(), entry, default_mode="auto", now=_NOW)
    assert form.repo is None
    assert form.folder == str(BOARD_SESSION_A.cwd)
    assert form.tasks == ()


@pytest.mark.parametrize(
    "entry",
    [
        None,
        OrphanEntry(
            orphan=Orphan(meute_id="x", pane_id="%1", command="claude", cwd="/srv", dead=False)
        ),
    ],
)
def test_open_without_a_selection_has_no_repo_and_no_folder(entry: BoardEntry | None) -> None:
    form = open_form(_data(), entry, default_mode="auto", now=_NOW)
    assert form.repo is None
    assert form.folder == ""
    assert [repo.name for repo in form.repos] == ["meute", "notes"]
    assert form.agent is AgentKind.CLAUDE


def test_modes_start_with_the_default_then_sorted() -> None:
    form = open_form(_data(), None, default_mode="plan", now=_NOW)
    assert form.modes[0] == "plan"
    assert form.modes[1:] == tuple(sorted(PERMISSION_MODES - {"plan"}))
    assert form.mode == 0


def test_repo_prefill_uses_the_last_agent() -> None:
    data = replace(_data(), last_agents={RepoId(2): AgentKind.BASH})
    form = open_form(data, RepoEntry(repo=BOARD_REPO_2), default_mode="auto", now=_NOW)
    assert form.agent is AgentKind.BASH


def test_busy_holds_the_resolved_folders_of_live_sessions(tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(tmp_path)
    session = replace(BOARD_SESSION_A, cwd=link)
    data = replace(_data(), sessions=(SessionRow(session=session, has_pane=True, displayed=False),))
    form = open_form(data, None, default_mode="auto", now=_NOW)
    assert form.busy == frozenset({tmp_path.resolve()})


def _visited(form: LaunchForm, count: int) -> list[FormField]:
    seen: list[FormField] = []
    for _ in range(count):
        seen.append(form.field)
        form = move(form, 1)
    return seen


def test_move_cycles_and_skips_task_and_mode_for_bash() -> None:
    assert _visited(_form(), 7) == [
        FormField.TYPE,
        FormField.REPO,
        FormField.FOLDER,
        FormField.TITLE,
        FormField.TASK,
        FormField.MODE,
        FormField.TYPE,
    ]
    bash = replace(_form(), agent=AgentKind.BASH)
    assert _visited(bash, 5) == [
        FormField.TYPE,
        FormField.REPO,
        FormField.FOLDER,
        FormField.TITLE,
        FormField.TYPE,
    ]
    assert move(bash, -1).field is FormField.TITLE
    assert move(_form(), -1).field is FormField.MODE


def test_every_transition_clears_the_error() -> None:
    form = replace(_form(), error="boom")
    assert move(form, 1).error is None
    assert choose(form, 1, _data(), _NOW).error is None
    assert type_text(replace(form, field=FormField.TITLE), "a").error is None
    assert erase(replace(form, field=FormField.TITLE)).error is None


def test_choose_type_switches_between_claude_and_bash() -> None:
    form = choose(_form(), 1, _data(), _NOW)
    assert form.agent is AgentKind.BASH
    assert choose(form, 1, _data(), _NOW).agent is AgentKind.CLAUDE
    assert choose(_form(), -1, _data(), _NOW).agent is AgentKind.BASH


def test_choose_repo_replaces_folder_and_tasks_and_ends_on_none() -> None:
    data = _data()
    form = replace(_form(RepoEntry(repo=BOARD_REPO_2)), field=FormField.REPO, task=None)
    meute = choose(form, 1, data, _NOW)
    assert meute.repo == 1
    assert meute.folder == str(BOARD_REPO_1.path)
    assert [task.id for task in meute.tasks] == [2, 1]
    picked = replace(meute, task=1)
    none = choose(picked, 1, data, _NOW)
    assert none.repo is None
    assert none.folder == str(BOARD_REPO_1.path)
    assert none.tasks == ()
    assert none.task is None
    back = choose(none, 1, data, _NOW)
    assert back.repo == 0
    assert choose(back, -1, data, _NOW).repo is None


def test_choose_repo_with_no_repository_stays_on_none() -> None:
    data = replace(_data(), repos=())
    form = open_form(data, None, default_mode="auto", now=_NOW)
    assert choose(replace(form, field=FormField.REPO), 1, data, _NOW).repo is None


def test_choose_task_cycles_through_none_and_the_tasks() -> None:
    data = _data()
    form = replace(_form(RepoEntry(repo=BOARD_REPO_1)), field=FormField.TASK)
    one = choose(form, 1, data, _NOW)
    assert one.task == 0
    two = choose(one, 1, data, _NOW)
    assert two.task == 1
    assert choose(two, 1, data, _NOW).task is None
    assert choose(form, -1, data, _NOW).task == 1


def test_choose_mode_cycles() -> None:
    form = replace(_form(), field=FormField.MODE)
    assert choose(form, 1, _data(), _NOW).mode == 1
    assert choose(form, -1, _data(), _NOW).mode == len(form.modes) - 1


def test_choose_does_nothing_on_a_text_field() -> None:
    form = replace(_form(), field=FormField.TITLE)
    assert choose(form, 1, _data(), _NOW) == form


def test_typing_edits_only_folder_and_title() -> None:
    form = replace(_form(), field=FormField.TITLE)
    form = type_text(form, "fix")
    form = type_text(form, " ")
    form = type_text(form, "it\n\x1b[2J")
    assert form.title == "fix it \ufffd[2J"
    assert erase(form).title == "fix it \ufffd[2"
    assert erase(replace(form, title="")).title == ""
    folder = replace(form, field=FormField.FOLDER, folder="/a")
    assert type_text(folder, "/b").folder == "/a/b"
    assert erase(folder).folder == "/"
    typed = replace(form, field=FormField.MODE)
    assert type_text(typed, "x") == typed
    assert erase(typed) == typed


def test_a_paste_is_collapsed_on_one_line() -> None:
    form = replace(_form(), field=FormField.TITLE)
    assert type_text(form, "a\n  b\tc").title == "a b c"


def test_typing_is_bounded() -> None:
    form = replace(_form(), field=FormField.TITLE)
    assert len(type_text(form, "x" * 10_000).title) <= 200


def test_form_action_claude_carries_task_mode_and_title() -> None:
    form = replace(
        _form(RepoEntry(repo=BOARD_REPO_1)), task=0, title="  fix  ", mode=1, worktree=NoWorktree()
    )
    action = form_action(form, BOARD_HOME)
    assert action == LaunchClaude(
        cwd=BOARD_REPO_1.path,
        repo_id=RepoId(1),
        title="fix",
        task_id=TaskId(2),
        permission_mode=form.modes[1],
    )


def test_form_action_bash_ignores_task_and_mode_and_an_empty_title_is_none() -> None:
    form = replace(
        _form(RepoEntry(repo=BOARD_REPO_1)),
        agent=AgentKind.BASH,
        task=0,
        title=" ",
        worktree=NoWorktree(),
    )
    assert form_action(form, BOARD_HOME) == LaunchBash(
        cwd=BOARD_REPO_1.path, repo_id=RepoId(1), title=None
    )


def test_form_action_without_repo_has_no_repo_id() -> None:
    form = replace(_form(), folder="/srv/work")
    action = form_action(form, BOARD_HOME)
    assert isinstance(action, LaunchClaude)
    assert action.repo_id is None
    assert action.task_id is None


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("~/x", Path("/home/me/x")),
        ("~", Path("/home/me")),
        ("  /srv  ", Path("/srv")),
        ("/srv/odd;", Path("/srv/odd;")),
    ],
)
def test_form_action_expands_and_strips_the_folder(typed: str, expected: Path) -> None:
    action = form_action(replace(_form(), folder=typed), BOARD_HOME)
    assert isinstance(action, LaunchClaude)
    assert action.cwd == expected


def test_form_action_refuses_a_relative_folder() -> None:
    assert form_action(replace(_form(), folder=" relative/path "), BOARD_HOME) == (
        "folder must be absolute: relative/path"
    )


def test_form_action_refuses_an_empty_folder() -> None:
    assert form_action(replace(_form(), folder="   "), BOARD_HOME) == "folder is empty"


def test_shares_folder_compares_resolved_paths(tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(tmp_path)
    busy = frozenset({tmp_path.resolve()})
    form = replace(_form(), busy=busy, folder=str(link))
    assert shares_folder(form, BOARD_HOME)
    assert not shares_folder(replace(form, folder=str(tmp_path / "other")), BOARD_HOME)
    assert not shares_folder(replace(form, folder=""), BOARD_HOME)
    assert not shares_folder(replace(form, folder="relative"), BOARD_HOME)
    home_busy = replace(form, busy=frozenset({Path("/home/me").resolve()}), folder="~")
    assert shares_folder(home_busy, BOARD_HOME)


_STEP = st.sampled_from([-1, 1])
_OPERATION = st.one_of(
    st.tuples(st.just("move"), _STEP),
    st.tuples(st.just("choose"), _STEP),
    st.tuples(st.just("type"), st.text(max_size=8)),
    st.tuples(st.just("erase"), st.just(0)),
)


@settings(max_examples=60, deadline=None)
@given(operations=st.lists(_OPERATION, max_size=25))
def test_any_moves_keep_the_indexes_valid(operations: list[tuple[str, object]]) -> None:
    data = _data()
    form = open_form(data, RepoEntry(repo=BOARD_REPO_1), default_mode="auto", now=_NOW)
    for name, argument in operations:
        match name:
            case "move":
                form = move(form, int(str(argument)))
            case "choose":
                form = choose(form, int(str(argument)), data, _NOW)
            case "type":
                form = type_text(form, str(argument))
            case _:
                form = erase(form)
        assert form.repo is None or 0 <= form.repo < len(form.repos)
        assert form.task is None or 0 <= form.task < len(form.tasks)
        assert 0 <= form.mode < len(form.modes)
        assert form.agent is not AgentKind.BASH or form.field not in {
            FormField.TASK,
            FormField.MODE,
        }
        assert "\n" not in form.title + form.folder


def test_a_session_without_repo_relaunches_its_own_type() -> None:
    entry = SessionEntry(row=SessionRow(session=BOARD_SESSION_A, has_pane=True, displayed=False))
    assert open_form(_data(), entry, default_mode="auto", now=_NOW).agent is AgentKind.BASH
