"""JSON value types shared by the serialisers of meute.core."""

import json
from typing import TypeGuard

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]


def _is_object(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def parse_json_object(text: str) -> dict[str, object]:
    """Return the string-keyed entries of the JSON object in `text`.

    Raises:
        ValueError: `text` is not valid JSON or not a JSON object.
    """
    loaded: object = json.loads(text)  # pyright: ignore[reportAny] — json.loads returns Any
    if not _is_object(loaded):
        message = "payload is not a JSON object"
        raise ValueError(message)
    return {key: value for key, value in loaded.items() if isinstance(key, str)}
