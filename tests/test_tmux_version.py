import pytest
from hypothesis import given
from hypothesis import strategies as st

from meute.tmux.client import Tmux, _classify_version  # pyright: ignore[reportPrivateUsage] — tested directly
from meute.tmux.errors import NotInstalled, TooOld
from meute.tmux.parse import MIN_VERSION, TmuxVersion, parse_version


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("tmux 3.5a", TmuxVersion(major=3, minor=5)),
        ("tmux 3.2", TmuxVersion(major=3, minor=2)),
        ("tmux next-3.6", TmuxVersion(major=3, minor=6)),
        ("tmux 2.9a", TmuxVersion(major=2, minor=9)),
        ("tmux 3.10", TmuxVersion(major=3, minor=10)),
        ("tmux master", None),
        ("tmux openbsd-7.6", None),
        ("", None),
    ],
)
def test_parse_version(text: str, expected: TmuxVersion | None) -> None:
    assert parse_version(text) == expected


@given(st.text())
def test_parse_version_never_raises(text: str) -> None:
    parse_version(text)


def test_versions_compare() -> None:
    assert TmuxVersion(major=3, minor=1) < MIN_VERSION
    assert TmuxVersion(major=3, minor=10) > TmuxVersion(major=3, minor=2)


def test_too_old_version_message() -> None:
    assert str(TooOld("2.9a")) == "tmux 2.9a is too old: meute needs tmux 3.2 or later"
    with pytest.raises(TooOld) as raised:
        _classify_version("tmux 2.9a")
    assert raised.value.found == "2.9a"


def test_unreadable_version_is_accepted() -> None:
    assert _classify_version("tmux openbsd-7.6") is None
    assert _classify_version("tmux 3.5a") == TmuxVersion(major=3, minor=5)


def test_not_installed_message() -> None:
    assert str(NotInstalled()) == (
        "tmux not found: meute needs tmux 3.2 or later (for example: sudo apt install tmux)"
    )


def test_missing_binary_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(NotInstalled):
        Tmux(socket="meute-test-missing").run("ls")
