from pathlib import Path

import pytest

from meute.git.kind import RepoKind, detect_kind


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"Cargo.toml": ""}, RepoKind.RUST),
        ({"Cargo.toml": "", "package.json": ""}, RepoKind.RUST),
        ({"angular.json": ""}, RepoKind.ANGULAR),
        ({"package.json": "", "angular.json": ""}, RepoKind.ANGULAR),
        ({"package.json": ""}, RepoKind.NODE),
        ({"pyproject.toml": "dependencies = ['FastAPI']"}, RepoKind.FASTAPI),
        ({"requirements.txt": "fastapi==0.1"}, RepoKind.FASTAPI),
        ({"package.json": "", "requirements.txt": "fastapi"}, RepoKind.NODE),
        ({"pyproject.toml": "[project]"}, RepoKind.PYTHON),
        ({"requirements.txt": "requests"}, RepoKind.PYTHON),
        ({"setup.py": "fastapi"}, RepoKind.PYTHON),
        ({}, None),
        ({"README.md": ""}, None),
    ],
)
def test_detect_kind(tmp_path: Path, files: dict[str, str], expected: RepoKind | None) -> None:
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    assert detect_kind(tmp_path) is expected


def test_kind_values() -> None:
    assert [kind.value for kind in RepoKind] == ["rust", "angular", "node", "fastapi", "python"]


def test_unreadable_file_counts_as_present_without_text(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe fastapi")
    assert detect_kind(tmp_path) is RepoKind.PYTHON


def test_directory_named_like_a_marker_is_not_a_marker(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").mkdir()
    assert detect_kind(tmp_path) is None
