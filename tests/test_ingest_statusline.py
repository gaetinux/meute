"""`meute ingest statusline`: records samples, prints a line, never fails."""

import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import Sandbox
from meute import ingest
from meute.core.db.rows import as_integer, fetch_one
from meute.core.db.sessions import create_session
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Unknown
from meute.ingest.statusline import run_statusline
from support import claude_statusline_fixture

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")
ESCAPE = re.compile(r"\033\[[0-9;]*m")
ENV = {"COLUMNS": "200"}


def payload(name: str = "statusline-2") -> str:
    return json.dumps(claude_statusline_fixture(name))


def run(
    box: Sandbox, stdin: str, *, session: str | None = str(SID)
) -> subprocess.CompletedProcess[str]:
    env = dict(ENV)
    if session is not None:
        env["MEUTE_SESSION"] = session
    return box.run("ingest", "statusline", env=env, stdin=stdin)


def count(box: Sandbox, table: str) -> int:
    with box.db() as db:
        row = fetch_one(db.conn, f"SELECT COUNT(*) FROM {table}")  # noqa: S608 — fixed names
        assert row is not None
        return as_integer(row[0])


def write_config(box: Sandbox, text: str) -> None:
    path = box.root / "config/meute/config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")


def log_text(box: Sandbox) -> str:
    log = box.root / "state/meute/ingest.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.fixture
def seeded(sandbox: Sandbox) -> Sandbox:
    with sandbox.db() as db:
        create_session(
            db,
            NewSession(
                id=SID, agent=AgentKind.CLAUDE, title="c", cwd=Path("/work"), state=Unknown()
            ),
        )
    return sandbox


def test_statusline_prints_even_for_unknown_session(sandbox: Sandbox) -> None:
    result = run(sandbox, payload(), session=None)
    assert result.returncode == 0
    visible = ESCAPE.sub("", result.stdout)
    assert "Opus 5.5" in visible
    assert "5h 27%" in visible
    assert "OFF-PEAK" in visible  # 04:30 in New York on a Wednesday: before the peak
    assert log_text(sandbox) == ""


def test_statusline_records_samples(seeded: Sandbox) -> None:
    result = run(seeded, payload())
    assert result.returncode == 0
    assert "5h 27%" in ESCAPE.sub("", result.stdout)
    assert count(seeded, "metric_samples") == 1
    assert count(seeded, "quota_samples") == 1
    assert log_text(seeded) == ""


def test_unknown_session_records_nothing(sandbox: Sandbox) -> None:
    sandbox.run("session", "list")  # creates the database
    run(sandbox, payload())
    assert count(sandbox, "metric_samples") == 0
    assert count(sandbox, "quota_samples") == 0


def test_valid_json_without_fields_prints_the_defaults(sandbox: Sandbox) -> None:
    result = run(sandbox, '{"model": 3}')
    assert (result.returncode, "Claude" in ESCAPE.sub("", result.stdout)) == (0, True)


@pytest.mark.parametrize("stdin", ["", "not json", "[1]"])
def test_a_payload_that_is_no_json_object_prints_nothing_and_is_logged(
    sandbox: Sandbox, stdin: str
) -> None:
    result = run(sandbox, stdin)
    assert (result.returncode, result.stdout) == (0, "")
    assert "ingest statusline" in log_text(sandbox)


def test_hostile_model_name_cannot_reach_the_terminal(sandbox: Sandbox) -> None:
    result = run(sandbox, json.dumps({"model": {"display_name": "\x1b]0;x\x07"}}))
    assert "\x1b" not in ESCAPE.sub("", result.stdout)
    assert "\x07" not in result.stdout


def test_huge_cost_is_recorded(seeded: Sandbox) -> None:
    run(seeded, '{"cost": {"total_cost_usd": 1e30, "total_duration_ms": 1000000000000000000000}}')
    assert count(seeded, "metric_samples") == 1
    assert log_text(seeded) == ""


def test_oversized_input_is_drained_and_logged(sandbox: Sandbox) -> None:
    result = run(sandbox, '{"x": "' + "a" * (2 * 1024 * 1024) + '"}')
    assert (result.returncode, result.stdout) == (0, "")
    assert "1 MiB" in log_text(sandbox)


def test_chain_replaces_the_output(seeded: Sandbox) -> None:
    write_config(seeded, "[statusline]\nchain = \"head -c 8; printf '!'\"\n")
    result = run(seeded, payload())
    assert result.stdout == payload()[:8] + "!"
    assert count(seeded, "metric_samples") == 1  # samples are recorded before the chain


@pytest.mark.parametrize(
    "chain", ["exit 3", "printf partial; exit 1", "true", "printf '  \\n'", "nonexistent-cmd-xyz"]
)
def test_failing_chain_falls_back(seeded: Sandbox, chain: str) -> None:
    write_config(seeded, f'[statusline]\nchain = "{chain}"\n')
    result = run(seeded, payload())
    assert result.returncode == 0
    assert "Opus 5.5" in ESCAPE.sub("", result.stdout)


def test_failing_or_slow_chain_falls_back(seeded: Sandbox) -> None:
    write_config(seeded, '[statusline]\nchain = "sleep 5"\n')
    started = time.monotonic()
    result = run(seeded, payload())
    assert time.monotonic() - started < 2
    assert "Opus 5.5" in ESCAPE.sub("", result.stdout)


def test_slow_chain_with_a_child_does_not_hold_the_pipe(seeded: Sandbox) -> None:
    write_config(seeded, '[statusline]\nchain = "sleep 5; echo late"\n')
    started = time.monotonic()
    result = run(seeded, payload())
    assert time.monotonic() - started < 2
    assert "late" not in result.stdout


def test_invalid_config_still_prints(seeded: Sandbox) -> None:
    write_config(seeded, "[statusline\n")
    result = run(seeded, payload())
    assert "Opus 5.5" in ESCAPE.sub("", result.stdout)
    assert "ingest statusline" in log_text(seeded)


def test_unknown_ingest_kind_drains_stdin_and_exits_zero(sandbox: Sandbox) -> None:
    result = sandbox.run("ingest", "bogus", stdin="x" * (1024 * 1024))
    assert (result.returncode, result.stdout) == (0, "")


def test_unknown_ingest_kind_reads_all_of_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin = io.StringIO("x" * 300_000)
    monkeypatch.setattr(sys, "stdin", stdin)
    assert ingest.run(["bogus"]) == 0
    assert stdin.read() == ""


def test_chain_with_an_escaped_descendant_still_returns_quickly(seeded: Sandbox) -> None:
    write_config(seeded, '[statusline]\nchain = "setsid sleep 5 & echo partial"\n')
    started = time.monotonic()
    result = run(seeded, payload())
    assert time.monotonic() - started < 2
    assert "Opus 5.5" in ESCAPE.sub("", result.stdout)


def test_chain_with_a_background_descendant_holding_stdout(seeded: Sandbox) -> None:
    write_config(seeded, '[statusline]\nchain = "(sleep 5) & echo partial"\n')
    started = time.monotonic()
    result = run(seeded, payload())
    assert time.monotonic() - started < 2
    assert "Opus 5.5" in ESCAPE.sub("", result.stdout)


def test_chain_receives_the_original_bytes(
    seeded: Sandbox, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(name, str(seeded.root / name.split("_")[1].lower()))
    write_config(seeded, f'[statusline]\nchain = "cat > {tmp_path}/got; echo ok"\n')
    stdin = io.StringIO('{"model": {"display_name": "caf\udce9"}}')
    stdout = io.StringIO()
    run_statusline(stdin, stdout, dict(os.environ) | {"MEUTE_SESSION": str(SID)})
    assert stdout.getvalue() == "ok\n"
    assert (tmp_path / "got").read_bytes() == b'{"model": {"display_name": "caf\xe9"}}'


def test_stdin_is_read_and_a_line_printed_even_without_a_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_home() -> Path:
        message = "no home"
        raise RuntimeError(message)

    monkeypatch.setattr(Path, "home", no_home)
    stdin = io.StringIO(payload())
    stdout = io.StringIO()
    run_statusline(stdin, stdout, {})
    assert stdin.read() == ""
    assert "Opus 5.5" in ESCAPE.sub("", stdout.getvalue())
