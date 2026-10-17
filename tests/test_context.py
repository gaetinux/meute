"""Local zone and clock resolution of the command line."""

from datetime import tzinfo
from zoneinfo import ZoneInfo

import pytest

from conftest import Sandbox
from meute.cli.context import current_time, local_zone

_BAD_TZ = ["Nope/Zone", "UTC0", ":Europe/Paris", "CET-1CEST,M3.5.0,M10.5.0/3", "Europe"]


@pytest.mark.parametrize("value", _BAD_TZ)
def test_local_zone_never_raises(value: str) -> None:
    assert isinstance(local_zone({"TZ": value}), tzinfo)


def test_local_zone_uses_valid_iana_name() -> None:
    assert local_zone({"TZ": "Europe/Paris"}) == ZoneInfo("Europe/Paris")


def test_local_zone_accepts_leading_colon() -> None:
    assert local_zone({"TZ": ":Europe/Paris"}) == ZoneInfo("Europe/Paris")


def test_current_time_without_frozen_clock_is_aware() -> None:
    assert current_time({"TZ": "Nope/Zone"}).tzinfo is not None


def test_invalid_tz_does_not_crash_the_command(sandbox: Sandbox) -> None:
    result = sandbox.run("task", "list", env={"TZ": "Nope/Zone"})
    assert result.returncode == 0
    assert "Traceback" not in result.stderr
