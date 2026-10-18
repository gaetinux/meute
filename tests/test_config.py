from pathlib import Path

import pytest

from meute.core.config import (
    DEFAULT_CONFIG,
    Config,
    config_get,
    config_key,
    ensure_config,
    load_config,
    write_atomic,
)
from meute.core.errors import ConfigError, InvalidInput, MeuteError


def test_ensure_config_writes_default_once_and_never_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "sub/config.toml"
    assert ensure_config(path)
    assert path.read_text(encoding="utf-8") == DEFAULT_CONFIG
    path.write_text("# mine\n[ui]\nboard_width = 80\n", encoding="utf-8")
    assert not ensure_config(path)
    assert path.read_text(encoding="utf-8") == "# mine\n[ui]\nboard_width = 80\n"


def test_default_config_loads_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    assert load_config(path) == Config()
    assert Config().repos.roots == ("~/git",)
    assert Config().claude.permission_mode == "auto"
    assert (Config().ui.board_width, Config().ui.narrow_threshold) == (60, 120)
    assert (
        Config().quotas.peak_timezone,
        Config().quotas.peak_start_hour,
        Config().quotas.peak_end_hour,
    ) == ("America/New_York", 8, 14)


def test_missing_and_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[ui]\nboad_width = 1\nboard_width = 70\n[perso]\nx = 1\n", encoding="utf-8")
    config = load_config(path)
    assert config.ui.board_width == 70
    assert config.ui.narrow_threshold == 120


def test_invalid_toml_reports_path_and_line_without_touching_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    text = "[ui]\nboard_width = = 3\n"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert "config.toml" in str(info.value)
    assert "line 2" in str(info.value)
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize(
    ("text", "key"),
    [
        ('[ui]\nboard_width = "large"\n', "ui.board_width"),
        ("[ui]\nboard_width = true\n", "ui.board_width"),
        ("[ui]\nnarrow_threshold = 0\n", "ui.narrow_threshold"),
        ("[quotas]\npeak_end_hour = 25\n", "quotas.peak_end_hour"),
        ('[quotas]\npeak_timezone = "Mars/Olympus"\n', "quotas.peak_timezone"),
        ('[claude]\npermission_mode = "yolo"\n', "claude.permission_mode"),
        ('[repos]\nroots = "~/git"\n', "repos.roots"),
    ],
)
def test_wrong_values_are_config_errors_naming_the_key(tmp_path: Path, text: str, key: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert key in str(info.value)
    assert str(info.value).startswith(f"invalid configuration ({path}): ")


def test_config_get_returns_file_value_then_default(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[ui]\nboard_width = 72\n", encoding="utf-8")
    assert config_get(path, "ui.board_width") == "72"
    assert config_get(path, "claude.permission_mode") == "auto"
    assert config_get(path, "repos.roots") == '["~/git"]'


def test_config_get_lists_with_default_separators(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[repos]\nroots = ["~/a", "~/é"]\n', encoding="utf-8")
    assert config_get(path, "repos.roots") == '["~/a", "~/é"]'


@pytest.mark.parametrize("key", ["ui.nope", "nope", "ui"])
def test_config_get_rejects_unknown_key(tmp_path: Path, key: str) -> None:
    with pytest.raises(InvalidInput, match=f"unknown key: {key}"):
        config_get(tmp_path / "absent.toml", key)
    with pytest.raises(InvalidInput):
        config_key(key)


def test_config_key_splits_section_and_field() -> None:
    assert config_key("ui.board_width") == ("ui", "board_width")


def test_absent_file_yields_defaults_everywhere(tmp_path: Path) -> None:
    assert load_config(tmp_path / "absent.toml") == Config()
    assert config_get(tmp_path / "absent.toml", "ui.board_width") == "60"


def test_unreadable_path_is_an_os_error_not_defaults(tmp_path: Path) -> None:
    with pytest.raises(OSError):  # noqa: PT011 — any OSError subtype (IsADirectoryError)
        load_config(tmp_path)
    with pytest.raises(OSError):  # noqa: PT011 — any OSError subtype (IsADirectoryError)
        config_get(tmp_path, "ui.board_width")


def test_write_atomic_creates_parents_and_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "a/b/f.txt"
    write_atomic(path, "x")
    assert path.read_text(encoding="utf-8") == "x"
    assert [p.name for p in path.parent.iterdir()] == ["f.txt"]


def test_write_atomic_cleans_up_on_failure(tmp_path: Path) -> None:
    target = tmp_path / "dir"
    target.mkdir()
    with pytest.raises(OSError):  # noqa: PT011 — replacing a directory fails with an OSError
        write_atomic(target, "x")
    assert [p.name for p in tmp_path.iterdir()] == ["dir"]


def test_errors_share_a_base() -> None:
    assert issubclass(InvalidInput, MeuteError)
    assert issubclass(ConfigError, MeuteError)


def test_non_utf8_file_is_a_config_error(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_bytes(b"# caf\xe9\n")
    with pytest.raises(ConfigError, match=r"config\.toml"):
        load_config(path)
    with pytest.raises(ConfigError, match=r"config\.toml"):
        config_get(path, "ui.board_width")


def test_ensure_config_on_a_dangling_symlink_creates_its_target(tmp_path: Path) -> None:
    link = tmp_path / "config.toml"
    target = tmp_path / "real/config.toml"
    link.symlink_to(target)
    assert ensure_config(link)
    assert link.is_symlink()
    assert target.read_text(encoding="utf-8") == DEFAULT_CONFIG


def test_default_config_has_keys_section(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    ensure_config(path)
    assert config_get(path, "keys.focus_board") == "M-p"
    assert config_get(path, "keys.focus_main") == "M-o"


@pytest.mark.parametrize("field", ["focus_board", "focus_main"])
@pytest.mark.parametrize("value", [r"M-p \; kill-server", "", "M p", "a" * 21])
def test_keys_must_be_tmux_keys(tmp_path: Path, field: str, value: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f"[keys]\n{field} = '{value}'\n", encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_config(path)
    assert str(info.value).endswith(f"keys.{field}: expected a tmux key such as M-p")


@pytest.mark.parametrize("value", ["M-N", "F5", "C-M-x"])
def test_keys_accept_letters_digits_and_dashes(tmp_path: Path, value: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f'[keys]\nfocus_board = "{value}"\nfocus_main = "{value}"\n', encoding="utf-8")
    keys = load_config(path).keys
    assert (keys.focus_board, keys.focus_main) == (value, value)


def test_default_config_has_statusline_section(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    ensure_config(path)
    assert config_get(path, "statusline.chain") == ""
    assert Config().statusline.chain == ""
    assert load_config(path).statusline.chain == ""


def test_statusline_chain_is_a_string(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[statusline]\nchain = "echo hi"\n', encoding="utf-8")
    assert load_config(path).statusline.chain == "echo hi"
    path.write_text("[statusline]\nchain = 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"statusline\.chain"):
        load_config(path)
