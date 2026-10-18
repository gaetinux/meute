"""`local_zone` lives in the core and stays importable from the CLI context."""

from datetime import tzinfo
from zoneinfo import ZoneInfo

from meute.cli import context
from meute.core.clock import local_zone


def test_local_zone_is_shared_with_the_cli() -> None:
    assert context.local_zone is local_zone
    assert local_zone({"TZ": "Europe/Paris"}) == ZoneInfo("Europe/Paris")
    assert isinstance(local_zone({}), tzinfo)
