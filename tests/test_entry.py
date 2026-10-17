import importlib.metadata
import json
import subprocess
import sys

import pytest


def run_meute(args: list[str], stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "meute", *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_version_prints_name_and_version() -> None:
    result = run_meute(["--version"])
    assert result.returncode == 0
    assert result.stdout == f"meute {importlib.metadata.version('meute')}\n"


def test_ingest_hook_is_silent_and_succeeds() -> None:
    payload = json.dumps({"session_id": "abc", "hook_event_name": "PostToolUse"})
    result = run_meute(["ingest", "hook", "PostToolUse"], payload)
    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    ("args", "stdin"),
    [
        (["ingest"], ""),
        (["ingest", "foo"], "not json"),
        (["ingest", "hook"], "{"),
        (["ingest", "statusline"], ""),
    ],
)
def test_ingest_never_fails(args: list[str], stdin: str) -> None:
    result = run_meute(args, stdin)
    assert result.returncode == 0
    assert result.stdout == ""


def test_unknown_command_fails() -> None:
    assert run_meute(["nope"]).returncode != 0
