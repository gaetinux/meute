"""Test configuration: hypothesis profiles chosen by `HYPOTHESIS_PROFILE`."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from hypothesis import settings

from meute.core.db.connection import Database
from support import FIXED

settings.register_profile("dev", max_examples=100)
settings.register_profile("ci", max_examples=1000)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture
def db() -> Generator[Database]:
    """An in-memory database with a fixed clock, closed after the test."""
    with Database.in_memory(clock=lambda: FIXED) as database:
        yield database


@pytest.fixture
def file_db(tmp_path: Path) -> Generator[tuple[Database, Path]]:
    """A file database with a fixed clock, and its path, closed after the test."""
    path = tmp_path / "meute.db"
    with Database.open(path, busy_timeout_ms=1000, clock=lambda: FIXED) as database:
        yield database, path
