"""Tests that kill mutants of the plan 5 code: MCP inputs, launch options, instructions."""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from meute.claude.context_arg import ContextFile, ContextText
from meute.claude.launch import claude_argv
from meute.claude.mcp_config import write_mcp_config
from meute.claude.settings import MEUTE_TOOLS, write_settings
from meute.core.config import config_get
from meute.core.config_validate import validate_config
from meute.core.db.connection import Database
from meute.core.db.projects import create_project, set_project_instructions
from meute.core.db.repos import link_repo, project_repos, sync_repos
from meute.core.db.sessions import create_session, link_session_task
from meute.core.db.tasks import create_task
from meute.core.errors import InvalidInput, NotFound
from meute.core.mcp_data import DueFilter, due_matches, task_summary_json
from meute.core.project import ProjectId
from meute.core.repo import NewRepo
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from meute.core.task import DueAt, TaskId
from support import USER, make_task, new_task

SID = SessionId("0b6f1d0e-0000-4000-8000-000000000005")


def _argv(**changes: object) -> tuple[str, ...]:
    return claude_argv(
        claude=Path("/bin/claude"),
        settings=Path("/s/settings.json"),
        session_id=SID,
        permission_mode="plan",
        title="t",
        **changes,  # pyright: ignore[reportArgumentType] — a test helper forwarding two optional parts
    )


def test_the_mcp_config_follows_the_settings_and_a_text_context_precedes_the_name() -> None:
    argv = _argv(mcp_config=Path("/s/mcp.json"), context=ContextText("be terse"))
    assert argv == (
        "/bin/claude", "--settings", "/s/settings.json", "--mcp-config", "/s/mcp.json",
        "--session-id", SID, "--permission-mode", "plan",
        "--append-system-prompt", "be terse", "--name=t",
    )  # fmt: skip


def test_a_file_context_uses_the_file_option() -> None:
    argv = _argv(context=ContextFile(Path("/s/context.md")))
    assert argv[-3:-1] == ("--append-system-prompt-file", "/s/context.md")
    assert "--mcp-config" not in argv


def test_the_mcp_config_file_is_indented_by_two(tmp_path: Path) -> None:
    path = write_mcp_config(tmp_path, SID, ["/usr/bin/meute"])
    text = path.read_text(encoding="utf-8")
    assert text.startswith('{\n  "mcpServers": {\n    "meute": {')
    assert json.loads(text)["mcpServers"]["meute"]["env"] == {"MEUTE_SESSION": SID}


def test_written_settings_carry_the_allowed_tools(tmp_path: Path) -> None:
    path = write_settings(tmp_path, SID, ["/usr/bin/meute"], MEUTE_TOOLS)
    assert json.loads(path.read_text(encoding="utf-8"))["permissions"] == {
        "allow": list(MEUTE_TOOLS)
    }
    plain = write_settings(tmp_path, SessionId("0b6f1d0e-0000-4000-8000-000000000006"), ["m"])
    assert "permissions" not in json.loads(plain.read_text(encoding="utf-8"))


def test_non_string_instructions_are_refused_with_their_key() -> None:
    with pytest.raises(InvalidInput, match=r"^claude\.instructions: expected a string$"):
        validate_config({"claude": {"instructions": 3}})


def test_config_get_reads_the_instructions(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[claude]\ninstructions = "Be terse."\n', encoding="utf-8")
    assert config_get(path, "claude.instructions") == "Be terse."


def test_a_task_summary_without_a_due_says_null() -> None:
    assert task_summary_json(make_task(1))["due"] is None


def test_today_is_read_in_the_zone_of_now_not_the_machine_zone() -> None:
    kiritimati = ZoneInfo("Pacific/Kiritimati")  # UTC+14, far from any machine zone
    now = datetime(2026, 10, 14, 1, 0, tzinfo=kiritimati)
    at = datetime(2026, 10, 13, 11, 30, tzinfo=ZoneInfo("UTC"))  # 01:30 on the 14th over there
    assert due_matches(DueAt(at=at), DueFilter.TODAY, now)


def test_linking_to_an_unknown_task_names_the_task(db: Database) -> None:
    create_session(
        db,
        NewSession(id=SID, agent=AgentKind.BASH, title="s", cwd=Path("/w"), state=Running()),
    )
    with pytest.raises(NotFound) as caught:
        link_session_task(db, SID, TaskId(99))
    assert (caught.value.entity, caught.value.ident) == ("task", "99")


def test_project_instructions_are_set_returned_and_cleared(db: Database) -> None:
    project = create_project(db, "p")
    set_project_instructions(db, project.id, "Tests first.")
    assert set_project_instructions(db, project.id, "Tests first.").instructions == "Tests first."
    assert set_project_instructions(db, project.id, "").instructions == ""


def test_instructions_of_an_unknown_project(db: Database) -> None:
    with pytest.raises(NotFound) as caught:
        set_project_instructions(db, ProjectId(99), "x")
    assert (caught.value.entity, caught.value.ident) == ("project", "99")


def test_a_project_lists_only_its_own_repositories(db: Database) -> None:
    first, second = sync_repos(
        db,
        [
            NewRepo(path=Path("/g/a"), name="a", kind=None),
            NewRepo(path=Path("/g/b"), name="b", kind=None),
        ],
    )
    mine, other = create_project(db, "mine"), create_project(db, "other")
    link_repo(db, mine.id, second.id)
    link_repo(db, other.id, first.id)
    assert [repo.name for repo in project_repos(db, mine.id)] == ["b"]
    assert project_repos(db, create_project(db, "empty").id) == []


def test_a_linked_task_survives_in_the_session(db: Database) -> None:
    create_session(
        db,
        NewSession(id=SID, agent=AgentKind.BASH, title="s", cwd=Path("/w"), state=Running()),
    )
    task = create_task(db, new_task("t"), USER)
    assert link_session_task(db, SID, task.id).task_id == task.id
