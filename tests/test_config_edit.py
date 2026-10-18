"""Tests of `config_set`: comment-preserving edits that never corrupt the file."""

from pathlib import Path

import pytest

from meute.cli.config_edit import config_set
from meute.core.config import DEFAULT_CONFIG, config_get, ensure_config
from meute.core.errors import ConfigError, InvalidInput


def test_set_preserves_comments_and_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("# keep me\n[ui]\nboard_width = 60 # width\n[perso]\nx = 1\n", encoding="utf-8")
    config_set(path, "ui.board_width", "72")
    text = path.read_text(encoding="utf-8")
    assert "# keep me" in text
    assert "board_width = 72 # width" in text
    assert "[perso]" in text
    assert config_get(path, "ui.board_width") == "72"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ui.nope", "1"),
        ("ui.board_width", "large"),
        ("ui.board_width", "true"),
        ("claude.permission_mode", "yolo"),
        ("ui.board_width", "60\n[evil]\nx = 1"),
    ],
)
def test_set_rejects_bad_keys_and_values_and_keeps_file(
    tmp_path: Path, key: str, value: str
) -> None:
    path = tmp_path / "config.toml"
    ensure_config(path)
    with pytest.raises(InvalidInput):
        config_set(path, key, value)
    assert path.read_text(encoding="utf-8") == DEFAULT_CONFIG


def test_set_on_absent_file_creates_it(tmp_path: Path) -> None:
    path = tmp_path / "absent.toml"
    config_set(path, "ui.board_width", "80")
    assert config_get(path, "ui.board_width") == "80"


def test_set_creates_a_missing_section(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[perso]\nx = 1\n", encoding="utf-8")
    config_set(path, "ui.board_width", "80")
    assert config_get(path, "ui.board_width") == "80"
    assert "[perso]" in path.read_text(encoding="utf-8")


def test_set_accepts_strings_and_lists(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    ensure_config(path)
    config_set(path, "claude.permission_mode", "plan")
    assert config_get(path, "claude.permission_mode") == "plan"
    config_set(path, "repos.roots", '["~/a", "~/b"]')
    assert config_get(path, "repos.roots") == '["~/a", "~/b"]'


def test_set_on_unparsable_file_raises_config_error_with_line(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[ui]\nboard_width = = 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="line 2"):
        config_set(path, "ui.board_width", "72")


def test_set_keeps_a_symlinked_config_a_symlink(tmp_path: Path) -> None:
    target = tmp_path / "dotfiles" / "config.toml"
    target.parent.mkdir()
    ensure_config(target)
    link = tmp_path / "config.toml"
    link.symlink_to(target)
    config_set(link, "ui.board_width", "72")
    assert link.is_symlink()
    assert config_get(target, "ui.board_width") == "72"


@pytest.mark.parametrize(
    "text",
    [
        "ui = { board_width = 60, narrow_threshold = 100 } # mine\n",
        "ui.board_width = 60\nui.narrow_threshold = 100\n",
    ],
)
def test_set_keeps_siblings_of_inline_and_dotted_sections(tmp_path: Path, text: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    config_set(path, "ui.board_width", "72")
    assert "narrow_threshold = 100" in path.read_text(encoding="utf-8")
    assert config_get(path, "ui.board_width") == "72"
    assert config_get(path, "ui.narrow_threshold") == "100"


def test_set_keeps_the_comment_of_an_inline_section(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("ui = { board_width = 60 } # mine\n", encoding="utf-8")
    config_set(path, "ui.board_width", "72")
    assert "# mine" in path.read_text(encoding="utf-8")


def test_set_refuses_a_section_that_is_not_a_table(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("ui = 5\n", encoding="utf-8")
    with pytest.raises(InvalidInput, match="ui: expected a table"):
        config_set(path, "ui.board_width", "72")
    assert path.read_text(encoding="utf-8") == "ui = 5\n"
