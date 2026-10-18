"""The ingest paths stay light: the hook path reaching the database, the statusline path."""

from pathlib import Path

from conftest import Sandbox
from meute.core.db.sessions import create_session
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Unknown

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")


def test_hook_with_a_session_and_a_database_skips_migrations_and_config(
    sandbox: Sandbox,
) -> None:
    with sandbox.db() as db:
        create_session(
            db,
            NewSession(id=SID, agent=AgentKind.CLAUDE, title="c", cwd=Path("/w"), state=Unknown()),
        )
    result = sandbox.run(
        "ingest", "hook", "PostToolUse", env={"MEUTE_SESSION": SID}, stdin='{"session_id": "x"}'
    )
    assert result.returncode == 0
    traced = sandbox.run(
        "ingest",
        "hook",
        "PostToolUse",
        env={"MEUTE_SESSION": SID, "PYTHONPROFILEIMPORTTIME": "1"},
        stdin='{"session_id": "x"}',
    )
    output = traced.stderr
    assert "meute.core.db.hook_apply" in output  # witness: open_existing was reached
    for name in ("meute.core.db.migrations", "meute.core.config", "tomllib"):
        assert name not in output


def test_statusline_without_a_config_file_skips_the_config_loader(sandbox: Sandbox) -> None:
    payload = (Path(__file__).parent / "fixtures/claude/2.1.302/statusline-1.json").read_text()
    traced = sandbox.run(
        "ingest", "statusline", env={"PYTHONPROFILEIMPORTTIME": "1"}, stdin=payload
    )
    assert "Opus 5.5" in traced.stdout  # witness: the line was printed
    assert "meute.core.config " not in traced.stderr.replace("\n", " \n")
    assert "tomllib" not in traced.stderr
