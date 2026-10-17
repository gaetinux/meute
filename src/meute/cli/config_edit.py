"""Editing the configuration file while keeping its comments and unknown keys."""

from pathlib import Path

import tomlkit
from tomlkit.container import OutOfOrderTableProxy
from tomlkit.exceptions import ParseError
from tomlkit.items import AbstractTable, Item

from meute.core.config import config_key, validate_config, write_atomic
from meute.core.errors import ConfigError, InvalidInput


def _parse_value(text: str) -> Item:
    """Read `text` as one TOML value, else as a string.

    `tomlkit.value` accepts nothing but a single value: text that carries a newline and a
    header (`60\\n[evil]`) is not a value, so it becomes a string and validation refuses it.
    """
    try:
        return tomlkit.value(text)
    except ParseError:
        return tomlkit.string(text)


def _read_document(path: Path) -> tomlkit.TOMLDocument:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return tomlkit.document()
    except UnicodeDecodeError as error:
        raise ConfigError(path, str(error)) from error
    try:
        return tomlkit.parse(raw)
    except ParseError as error:
        raise ConfigError(path, str(error)) from error


def config_set(path: Path, key: str, value: str) -> None:
    """Set `key` to `value` in the file at `path`, creating the file or section if needed.

    The value is a TOML value when `value` is exactly one (`72`, `["a"]`), else a string.
    A symbolic link is followed, so the link itself survives the write. Comments, unknown
    keys and the trailing comment of the replaced value are kept.

    Raises:
        InvalidInput: the key is unknown, or the file would no longer be a valid configuration;
            the file is then left untouched.
        ConfigError: the existing file cannot be parsed.
    """
    section_name, name = config_key(key)
    target = path.resolve()
    document = _read_document(target)
    if section_name not in document:
        document[section_name] = tomlkit.table()
    section = document.item(section_name)
    if not isinstance(section, (AbstractTable, OutOfOrderTableProxy)):
        message = f"{section_name}: expected a table"
        raise InvalidInput(message)
    section[name] = _parse_value(value)
    validate_config(document.unwrap())
    write_atomic(target, tomlkit.dumps(document))
