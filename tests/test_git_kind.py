import os
import threading
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


def _detect_within(folder: Path, seconds: float) -> RepoKind | None:
    """Run detect_kind in a daemon thread, so that a hang fails the test instead of blocking it."""
    found: list[RepoKind | None] = []
    worker = threading.Thread(target=lambda: found.append(detect_kind(folder)), daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        pytest.fail("detect_kind hung on a special file")
    return found[0]


def test_fifo_named_like_a_marker_is_never_opened(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "requirements.txt")
    assert _detect_within(tmp_path, 5) is None


def test_symlink_to_a_fifo_is_present_but_never_opened(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    (tmp_path / "requirements.txt").symlink_to(tmp_path / "pipe")
    assert _detect_within(tmp_path, 5) is RepoKind.PYTHON


def test_multibyte_text_cut_by_the_read_limit_is_still_read(tmp_path: Path) -> None:
    text = "fastapi" + "é" * 600_000  # the 1 MiB limit falls inside a two-byte character
    (tmp_path / "requirements.txt").write_text(text, encoding="utf-8")
    assert detect_kind(tmp_path) is RepoKind.FASTAPI
