"""Compact JSON output."""

import json

import typer

from meute.core.json_types import JsonValue


def echo_json(value: JsonValue) -> None:
    """Print `value` as compact JSON on one line."""
    typer.echo(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
