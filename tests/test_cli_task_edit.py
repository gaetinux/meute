"""End-to-end tests of the commands that change tasks."""

import pytest
from syrupy.assertion import SnapshotAssertion
from typer.testing import CliRunner

from conftest import Sandbox
from meute.cli import app


def with_task(sandbox: Sandbox) -> None:
    assert sandbox.run("task", "add", "Review the PR").returncode == 0


def test_status_blocked_requires_reason_then_shows_it(sandbox: Sandbox) -> None:
    with_task(sandbox)
    refused = sandbox.run("task", "status", "1", "blocked")
    assert (refused.returncode, refused.stderr) == (
        1,
        "meute: a blocked task needs a non-empty reason\n",
    )
    done = sandbox.run("task", "status", "1", "blocked", "--reason", "waiting for review")
    assert done.stdout == "#1 ✕ Review the PR · blocked: waiting for review\n"


def test_status_unknown_kind_exits_1(sandbox: Sandbox) -> None:
    with_task(sandbox)
    result = sandbox.run("task", "status", "1", "finished")
    assert (result.returncode, result.stderr) == (1, "meute: unknown status: finished\n")


def test_stale_expected_version_exits_3_with_current_state(
    sandbox: Sandbox, snapshot: SnapshotAssertion
) -> None:
    with_task(sandbox)
    sandbox.run("task", "edit", "1", "--title", "A")
    result = sandbox.run("task", "edit", "1", "--title", "B", "--expected-version", "1")
    assert result.returncode == 3
    assert result.stderr == snapshot


def test_rm_without_yes_off_tty_refuses(sandbox: Sandbox) -> None:
    with_task(sandbox)
    refused = sandbox.run("task", "rm", "1")
    assert (refused.returncode, refused.stderr) == (
        1,
        "meute: confirmation required: rerun with --yes\n",
    )
    assert sandbox.run("task", "show", "1").returncode == 0
    assert sandbox.run("task", "rm", "1", "--yes").stdout == "Deleted: #1\n"
    assert sandbox.run("task", "show", "1").returncode == 4


def test_note_then_show_lists_it_with_author(sandbox: Sandbox) -> None:
    with_task(sandbox)
    assert sandbox.run("task", "note", "1", "Started").stdout == "Note added to #1\n"
    assert "] user: Started\n" in sandbox.run("task", "show", "1").stdout


def test_edit_invalid_due_and_priority_are_rejected(sandbox: Sandbox) -> None:
    with_task(sandbox)
    due = sandbox.run("task", "edit", "1", "--due", "soon")
    assert (due.returncode, due.stderr) == (1, "meute: invalid due date: soon\n")
    priority = sandbox.run("task", "edit", "1", "--priority", "top")
    assert (priority.returncode, priority.stderr) == (1, "meute: unknown priority: top\n")


def test_edit_sets_and_clears_due_and_project(sandbox: Sandbox) -> None:
    with_task(sandbox)
    sandbox.run("project", "add", "meute")
    set_ = sandbox.run(
        "task", "edit", "1", "--project", "meute", "--due", "tomorrow", "--priority", "high"
    )
    assert set_.stdout == "#1 · ! Review the PR @meute · tomorrow\n"
    cleared = sandbox.run("task", "edit", "1", "--project", "none", "--due", "none")
    assert cleared.stdout == "#1 · ! Review the PR\n"
    nope = sandbox.run("task", "edit", "1", "--project", "nope")
    assert (nope.returncode, nope.stderr) == (
        1,
        "meute: unknown project: nope (projects: meute)\n",
    )


def test_edit_description_shows_in_detail(sandbox: Sandbox) -> None:
    with_task(sandbox)
    assert sandbox.run("task", "edit", "1", "--description", "Details here").returncode == 0
    assert "Details here" in sandbox.run("task", "show", "1").stdout


def _tty_rm(sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch, answer: str) -> tuple[int, str, str]:
    for key, value in {
        "HOME": str(sandbox.root / "home"),
        "XDG_CONFIG_HOME": str(sandbox.root / "config"),
        "XDG_DATA_HOME": str(sandbox.root / "data"),
        "XDG_STATE_HOME": str(sandbox.root / "state"),
        "MEUTE_NOW": "2026-10-14T10:30[Europe/Paris]",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("meute.cli.task_edit_commands.stdin_is_terminal", lambda: True)
    result = CliRunner().invoke(app, ["task", "rm", "1"], input=answer)
    return result.exit_code, result.stdout, result.stderr


@pytest.mark.parametrize("answer", ["y\n", "yes\n", "YES\n"])
def test_rm_on_tty_confirms(sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    with_task(sandbox)
    code, out, _ = _tty_rm(sandbox, monkeypatch, answer)
    assert (code, out) == (0, "Delete #1 \u201cReview the PR\u201d? [y/N] Deleted: #1\n")


@pytest.mark.parametrize("answer", ["n\n", "\n", "maybe\n"])
def test_rm_on_tty_cancels(sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    with_task(sandbox)
    code, out, _ = _tty_rm(sandbox, monkeypatch, answer)
    assert code != 0
    assert out.startswith("Delete #1")
    assert sandbox.run("task", "show", "1").returncode == 0
