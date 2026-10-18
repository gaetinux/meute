from pathlib import Path

import pytest

from meute.core.paths import Paths, display_path

H = Path("/h")


def test_from_roots_appends_meute_segments() -> None:
    p = Paths.from_roots(config_home=Path("/t/c"), data_home=Path("/t/d"), state_home=Path("/t/s"))
    assert p == Paths(
        config_file=Path("/t/c/meute/config.toml"),
        db_file=Path("/t/d/meute/meute.db"),
        state_dir=Path("/t/s/meute"),
    )


def test_from_env_uses_xdg_variables() -> None:
    env = {"XDG_CONFIG_HOME": "/x/c", "XDG_DATA_HOME": "/x/d", "XDG_STATE_HOME": "/x/s"}
    assert Paths.from_env(env, home=H) == Paths.from_roots(
        config_home=Path("/x/c"), data_home=Path("/x/d"), state_home=Path("/x/s")
    )


def test_from_env_defaults_under_home() -> None:
    p = Paths.from_env({}, home=H)
    assert (p.config_file, p.db_file, p.state_dir) == (
        H / ".config/meute/config.toml",
        H / ".local/share/meute/meute.db",
        H / ".local/state/meute",
    )


@pytest.mark.parametrize("value", ["", "relative/dir"])
def test_from_env_ignores_empty_and_relative_values(value: str) -> None:
    env: dict[str, str] = dict.fromkeys(
        ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"), value
    )
    assert Paths.from_env(env, home=H) == Paths.from_env({}, home=H)


def test_ensure_dirs_creates_parent_directories(tmp_path: Path) -> None:
    p = Paths.from_roots(
        config_home=tmp_path / "c", data_home=tmp_path / "d", state_home=tmp_path / "s"
    )
    p.ensure_dirs()
    for name in ("c", "d", "s"):
        assert (tmp_path / name / "meute").is_dir()


@pytest.mark.parametrize(
    ("path", "home", "expected"),
    [
        ("/h", "/h", "~"),
        ("/h/git/api", "/h", "~/git/api"),
        ("/srv/api", "/h", "/srv/api"),
        ("/h/git", None, "/h/git"),
        ("/h2/api", "/h", "/h2/api"),
    ],
)
def test_display_path(path: str, home: str | None, expected: str) -> None:
    assert display_path(Path(path), None if home is None else Path(home)) == expected
