"""End-to-end tests of the task commands."""

from syrupy.assertion import SnapshotAssertion

from conftest import Sandbox
from meute.core.config import DEFAULT_CONFIG
from meute.core.db.task_notes import add_note
from meute.core.task import TaskId
from support import CLAUDE, USER, load_json, seed_mixed


def test_add_then_list_shows_spec_line(sandbox: Sandbox) -> None:
    assert sandbox.run("project", "add", "meute").returncode == 0
    added = sandbox.run("task", "add", "Review", "the", "PR", "@meute", "!", ">tomorrow")
    assert (added.returncode, added.stdout) == (
        0,
        "Created: #1 · ! Review the PR @meute · tomorrow\n",
    )
    assert sandbox.run("task", "list").stdout == "#1 · ! Review the PR @meute · tomorrow\n"


def test_unknown_project_creates_nothing(sandbox: Sandbox) -> None:
    sandbox.run("project", "add", "meute")
    result = sandbox.run("task", "add", "x", "@meuet")
    assert result.returncode == 1
    assert result.stderr == "meute: unknown project: meuet (projects: meute)\n"
    assert sandbox.run("task", "list", "--all", "--json").stdout == "[]\n"


def test_unknown_project_without_any_project(sandbox: Sandbox) -> None:
    result = sandbox.run("task", "add", "x", "@nope")
    assert result.returncode == 1
    assert result.stderr == "meute: unknown project: nope (no projects)\n"


def test_dry_run_creates_nothing(sandbox: Sandbox) -> None:
    result = sandbox.run("task", "add", "--dry-run", "Pay", "!!", ">fri-2pm")
    assert result.stdout == "Parsed: · !! Pay · Fri Oct 16 2pm\n"
    assert sandbox.run("task", "list", "--json").stdout == "[]\n"


def test_show_missing_task_exits_4(sandbox: Sandbox) -> None:
    result = sandbox.run("task", "show", "42")
    assert (result.returncode, result.stderr) == (4, "meute: task not found: #42\n")


def test_first_run_writes_default_config(sandbox: Sandbox) -> None:
    sandbox.run("task", "list")
    config = sandbox.root / "config/meute/config.toml"
    assert config.read_text(encoding="utf-8") == DEFAULT_CONFIG


def test_list_status_done_includes_done_tasks(sandbox: Sandbox) -> None:
    with sandbox.db() as db:
        seed_mixed(db)
    assert (
        sandbox.run("task", "list", "--status", "done").stdout == "#5 ✓ Close the ticket @meute\n"
    )
    assert "Close the ticket" not in sandbox.run("task", "list").stdout


def test_list_unknown_status_exits_1(sandbox: Sandbox) -> None:
    result = sandbox.run("task", "list", "--status", "nope")
    assert (result.returncode, result.stderr) == (1, "meute: unknown status: nope\n")


def test_list_filters_by_project_and_floating(sandbox: Sandbox) -> None:
    with sandbox.db() as db:
        seed_mixed(db)
    in_project = sandbox.run("task", "list", "--project", "meute", "--all").stdout
    assert "Deploy" in in_project
    assert "Tidy the desk" not in in_project
    floating = sandbox.run("task", "list", "--floating").stdout
    assert "Tidy the desk" in floating
    assert "Deploy" not in floating
    unknown = sandbox.run("task", "list", "--project", "nope")
    assert unknown.returncode == 1
    assert "unknown project: nope (projects: meute)" in unknown.stderr
    both = sandbox.run("task", "list", "--project", "meute", "--floating")
    assert both.returncode == 2


def test_list_and_show_json(sandbox: Sandbox) -> None:
    with sandbox.db() as db:
        seed_mixed(db)
    listed = load_json(sandbox.run("task", "list", "--all", "--json").stdout)
    assert isinstance(listed, list)
    assert len(listed) == 8
    second = next(item for item in listed if isinstance(item, dict) and item["id"] == 2)
    assert second["due"] == {"kind": "date", "value": "2026-10-15"}
    assert second["project"] == {"id": 1, "name": "meute"}
    shown = load_json(sandbox.run("task", "show", "3", "--json").stdout)
    assert isinstance(shown, dict)
    assert shown["status"] == "blocked"
    assert shown["blocked_reason"] == "waiting for CI"
    assert shown["notes"] == []


def test_invalid_meute_now_names_the_variable(sandbox: Sandbox) -> None:
    result = sandbox.run("task", "list", env={"MEUTE_NOW": "not a date"})
    assert result.returncode == 1
    assert result.stderr.startswith("meute: invalid MEUTE_NOW: ")


def test_snapshot_task_list_mixed(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    with sandbox.db() as db:
        seed_mixed(db)
    assert sandbox.run("task", "list", "--all").stdout == snapshot


def test_snapshot_task_show_with_notes(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    with sandbox.db() as db:
        seed_mixed(db)
        add_note(db, TaskId(1), "First item done.", USER)
        add_note(db, TaskId(1), "Review still to do.", CLAUDE)
    assert sandbox.run("task", "show", "1").stdout == snapshot
