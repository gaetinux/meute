"""Tests added after mutmut: configuration validation messages, bounds and atomic writes."""

import os
import tempfile
from pathlib import Path
from typing import IO

import pytest

from meute.core import config as config_module
from meute.core.config import (
    Config,
    config_get,
    load_config,
    validate_config,
    write_atomic,
)
from meute.core.errors import InvalidInput


def test_defaults_when_every_section_is_empty() -> None:
    assert validate_config({}) == Config()
    ui = validate_config({"ui": {}}).ui
    assert (ui.board_width, ui.narrow_threshold) == (60, 120)
    quotas = validate_config({"quotas": {}}).quotas
    assert (quotas.peak_start_hour, quotas.peak_end_hour) == (8, 14)


@pytest.mark.parametrize("section", ["repos", "claude", "ui", "quotas"])
def test_a_section_must_be_a_table(section: str) -> None:
    with pytest.raises(InvalidInput, match=f"^{section}: expected a table$"):
        validate_config({section: 5})


@pytest.mark.parametrize(
    ("section", "key", "low", "high"),
    [
        ("ui", "board_width", 1, None),
        ("ui", "narrow_threshold", 1, None),
        ("quotas", "peak_start_hour", 0, 24),
        ("quotas", "peak_end_hour", 0, 24),
    ],
)
def test_integer_bounds_are_inclusive_and_explained(
    section: str, key: str, low: int, high: int | None
) -> None:
    def load(value: int) -> Config:
        return validate_config({section: {key: value}})

    expected = f"an integer >= {low}" if high is None else f"an integer between {low} and {high}"
    assert load(low) is not None
    if high is not None:
        assert load(high) is not None
    with pytest.raises(InvalidInput, match=f"^{section}.{key}: expected {expected}$"):
        load(low - 1)
    if high is not None:
        with pytest.raises(InvalidInput, match=f"^{section}.{key}: expected {expected}$"):
            load(high + 1)


def test_explicit_values_are_read_from_their_own_key() -> None:
    config = validate_config(
        {
            "ui": {"board_width": 70, "narrow_threshold": 90},
            "quotas": {"peak_start_hour": 9, "peak_end_hour": 17, "peak_timezone": "Europe/Paris"},
        }
    )
    assert (config.ui.board_width, config.ui.narrow_threshold) == (70, 90)
    assert (config.quotas.peak_start_hour, config.quotas.peak_end_hour) == (9, 17)


def test_roots_permission_mode_and_timezone_messages() -> None:
    with pytest.raises(InvalidInput, match=r"^repos\.roots: expected a list of strings$"):
        validate_config({"repos": {"roots": [1]}})
    with pytest.raises(
        InvalidInput,
        match=(
            r"^claude\.permission_mode: expected one of "
            r"acceptEdits, auto, bypassPermissions, dontAsk, manual, plan$"
        ),
    ):
        validate_config({"claude": {"permission_mode": "yolo"}})
    with pytest.raises(
        InvalidInput, match=r"^quotas\.peak_timezone: expected an IANA time zone name$"
    ):
        validate_config({"quotas": {"peak_timezone": "Nowhere/Land"}})


@pytest.mark.parametrize(
    ("key", "text"),
    [
        ("repos.roots", '["~/git"]'),
        ("claude.permission_mode", "manual"),
        ("ui.board_width", "60"),
        ("ui.narrow_threshold", "120"),
        ("quotas.peak_timezone", "America/New_York"),
        ("quotas.peak_start_hour", "8"),
        ("quotas.peak_end_hour", "14"),
    ],
)
def test_every_key_reads_its_default(tmp_path: Path, key: str, text: str) -> None:
    assert config_get(tmp_path / "absent.toml", key) == text


def test_config_get_reads_the_keys_of_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[quotas]\npeak_timezone = 'Europe/Paris'\npeak_start_hour = 9\n")
    assert config_get(path, "quotas.peak_timezone") == "Europe/Paris"
    assert config_get(path, "quotas.peak_start_hour") == "9"
    assert config_get(path, "quotas.peak_end_hour") == "14"


def test_load_config_decodes_utf8(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_bytes('[repos]\nroots = ["~/dépôt"]\n'.encode())
    assert load_config(path).repos.roots == ("~/dépôt",)


def test_atomic_write_stages_the_temporary_file_next_to_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tempfile.NamedTemporaryFile
    seen: list[dict[str, object]] = []

    def spy(mode: str, **kwargs: object) -> IO[str]:
        seen.append(kwargs)
        return real(mode, **kwargs)  # pyright: ignore[reportCallIssue, reportArgumentType, reportUnknownVariableType] — forwards the caller's keywords unchanged

    monkeypatch.setattr(config_module.tempfile, "NamedTemporaryFile", spy)
    target = tmp_path / "deep" / "config.toml"
    write_atomic(target, "é\n")
    assert [kwargs["dir"] for kwargs in seen] == [target.parent]
    assert target.read_bytes() == "é\n".encode()
    assert list(target.parent.iterdir()) == [target]


def test_failed_atomic_write_cleans_up_even_if_the_temporary_file_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "config.toml"

    def vanish_then_fail(_descriptor: int) -> None:
        for leftover in tmp_path.iterdir():
            leftover.unlink()
        message = "boom"
        raise OSError(message)

    monkeypatch.setattr(os, "fsync", vanish_then_fail)
    with pytest.raises(OSError, match=r"^boom$"):
        write_atomic(target, "x")
    assert list(tmp_path.iterdir()) == []


def test_non_string_timezone_gets_the_same_message() -> None:
    with pytest.raises(
        InvalidInput, match=r"^quotas\.peak_timezone: expected an IANA time zone name$"
    ):
        validate_config({"quotas": {"peak_timezone": 5}})
