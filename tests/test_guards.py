import ast
from pathlib import Path

import guards

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PACKAGE = SRC / "meute"


def _python_files(*roots: Path) -> list[Path]:
    return sorted(path for root in roots for path in root.rglob("*.py"))


def test_no_wildcard_case_in_src() -> None:
    offenders = {
        f"{path}:{line}"
        for path in _python_files(SRC)
        for line in guards.wildcard_cases(path.read_text(encoding="utf-8"))
    }
    assert offenders == set()


def test_every_suppression_has_a_reason() -> None:
    offenders = {
        f"{path}:{line}"
        for path in _python_files(SRC, ROOT / "tests")
        for line in guards.suppressions_without_reason(path.read_text(encoding="utf-8"))
    }
    assert offenders == set()


def test_packages_import_only_the_stdlib_and_their_allowed_meute_packages() -> None:
    offenders = {
        f"{path}: {name}"
        for package, allowed in guards.ALLOWED_MEUTE_IMPORTS.items()
        for path in _python_files(PACKAGE / package)
        for name in guards.foreign_imports(path.read_text(encoding="utf-8"), allowed)
    }
    # The entry point may only reach the hot path and the CLI (lazily), beside the stdlib.
    entry = PACKAGE / "_entry.py"
    offenders |= {
        f"{entry}: {name}"
        for name in guards.foreign_imports(entry.read_text(encoding="utf-8"), ("ingest", "cli"))
    }
    assert offenders == set()


def test_core_init_has_no_imports() -> None:
    # Eagerly importing the whole core package costs 40-50 % of the ingest budget (spike S6):
    # core/__init__.py never re-exports and ingest imports only the submodules it needs.
    tree = ast.parse((PACKAGE / "core" / "__init__.py").read_text(encoding="utf-8"))
    assert [n for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom)] == []
