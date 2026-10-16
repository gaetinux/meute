import subprocess
import sys

IMPORT_TIME_PREFIX = "import time:"


def import_time_output(args: list[str], stdin: str) -> str:
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-m", "meute", *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stderr


def imported_roots(args: list[str], stdin: str) -> set[str]:
    roots: set[str] = set()
    for line in import_time_output(args, stdin).splitlines():
        if line.startswith(IMPORT_TIME_PREFIX) and "|" in line:
            name = line.rsplit("|", 1)[1].strip()
            if name != "imported package":  # column header
                roots.add(name.split(".")[0])
    return roots


def test_ingest_path_imports_only_stdlib_and_meute() -> None:
    roots = imported_roots(["ingest", "hook", "PostToolUse"], "{}")
    # Interpreter start-up noise, not ours: _virtualenv bootstraps uv environments,
    # sitecustomize and apport_python_hook are injected by the distribution's site setup.
    allowed = set(sys.stdlib_module_names) | {
        "meute",
        "_virtualenv",
        "sitecustomize",
        "apport_python_hook",
    }
    assert roots - allowed == set()


def test_ingest_path_never_loads_the_cli() -> None:
    output = import_time_output(["ingest", "hook", "PostToolUse"], "{}")
    assert "meute.cli" not in output


def test_cli_path_loads_typer() -> None:
    assert "typer" in imported_roots(["--version"], "")
