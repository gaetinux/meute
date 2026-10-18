"""The welcome pane's text."""

from meute.cli.welcome import welcome_text
from meute.core.config import KeysConfig


def test_welcome_text_uses_configured_keys() -> None:
    keys = KeysConfig(
        focus_board="M-b",
        focus_main="C-o",
        next_attention="F7",
        previous_attention="F8",
        detach="F9",
    )
    assert welcome_text(keys) == (
        "meute\n"
        "\n"
        "Pick a session in the dashboard and press Enter, or click it.\n"
        "M-b: dashboard · C-o: main area\n"
        "F7 / F8: next / previous session that needs attention\n"
        "F9 or q in the dashboard: detach, everything keeps running\n"
        "Hold Shift to select text with the mouse."
    )
