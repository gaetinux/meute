"""Displayed text never carries control characters; JSON stays raw."""

from pathlib import Path
from uuid import uuid4

from conftest import Sandbox
from meute.core.db.sessions import create_session
from meute.core.db.task_notes import add_note
from meute.core.db.task_update import update_task
from meute.core.db.tasks import create_task
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Exited
from meute.core.status import Blocked
from meute.core.task import TaskId, TaskPatch, task_to_json
from support import USER, load_json, new_task

EVIL_TITLE = "ok\x1b]0;pwned\x07"


def _clean(text: str) -> bool:
    return "\x1b" not in text and "\x07" not in text


def test_task_list_and_show_emit_no_control_bytes(sandbox: Sandbox) -> None:
    with sandbox.db() as db:
        task = create_task(db, new_task(EVIL_TITLE), USER)
    listed = sandbox.run("task", "list")
    shown = sandbox.run("task", "show", str(task.id))
    assert _clean(listed.stdout)
    assert listed.stdout == "#1 · ok\ufffd]0;pwned\ufffd\n"
    assert _clean(shown.stdout)
    assert shown.stdout.startswith("#1 ok\ufffd]0;pwned\ufffd\n")


def test_json_stays_raw(sandbox: Sandbox) -> None:
    with sandbox.db() as db:
        task = create_task(db, new_task(EVIL_TITLE), USER)
    out = load_json(sandbox.run("task", "list", "--json").stdout)
    assert out == [{**task_to_json(task)}]


def test_notes_keep_their_line_breaks(sandbox: Sandbox) -> None:
    with sandbox.db() as db:
        task = create_task(db, new_task("t"), USER)
        add_note(db, TaskId(task.id), "line1\nline2\x1b[2J", USER)
    shown = sandbox.run("task", "show", str(task.id)).stdout
    assert _clean(shown)
    assert "line1\nline2\ufffd[2J" in shown


def test_session_list_emits_no_control_bytes(sandbox: Sandbox) -> None:
    folder = sandbox.root / "w\x1b[2Jdir"
    folder.mkdir()
    with sandbox.db() as db:
        create_session(
            db,
            NewSession(
                id=SessionId(str(uuid4())),
                agent=AgentKind.BASH,
                title="t\x1b[2J",
                cwd=Path(folder),
                state=Exited(code=0),
            ),
        )
    result = sandbox.run("session", "list", "--all")
    assert result.returncode == 0, result.stderr
    assert _clean(result.stdout), result.stdout
    assert "t\ufffd[2J" in result.stdout


def test_blocked_reason_is_sanitised_in_task_list(sandbox: Sandbox) -> None:
    with sandbox.db() as db:
        task = create_task(db, new_task("t"), USER)
        update_task(db, task.id, task.version, TaskPatch(status=Blocked(reason="x\x1b[2J")), USER)
    result = sandbox.run("task", "list")
    assert _clean(result.stdout)
    assert "blocked: x�[2J" in result.stdout


def test_error_line_is_sanitised(sandbox: Sandbox) -> None:
    result = sandbox.run("task", "list", "--project", "p\x1b[2J")
    assert result.returncode == 1
    assert result.stderr == "meute: unknown project: p\ufffd[2J (no projects)\n"
