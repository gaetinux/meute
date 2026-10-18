"""Helpers extracted by the branch simplification pass."""

from pathlib import Path

import pytest

from meute.cli.tmux_env import _write_if_changed  # pyright: ignore[reportPrivateUsage] — the write-only-when-changed rule is only reachable directly
from meute.core.db.rows import as_text
from meute.core.reconcile import first_by_id


def test_as_text_returns_a_string() -> None:
    assert as_text("abc") == "abc"


@pytest.mark.parametrize("value", [None, 3, b"x"])
def test_as_text_rejects_a_corrupt_value(value: object) -> None:
    with pytest.raises(ValueError, match=r"^corrupt row: expected text, got "):
        as_text(value)


def test_first_by_id_keeps_the_first_item_and_skips_none() -> None:
    items = [("a", 1), ("b", 2), ("a", 3), (None, 4)]
    assert first_by_id(items, lambda item: item[0]) == {"a": ("a", 1), "b": ("b", 2)}


def test_tmux_conf_is_rewritten_only_when_its_text_changes(tmp_path: Path) -> None:
    target = tmp_path / "tmux.conf"
    _write_if_changed(target, "one\n")
    first = target.stat().st_mtime_ns
    _write_if_changed(target, "one\n")
    assert target.stat().st_mtime_ns == first
    _write_if_changed(target, "two\n")
    assert target.read_text(encoding="utf-8") == "two\n"
