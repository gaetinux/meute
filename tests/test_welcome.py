"""The welcome pane's text."""

from meute.cli.welcome import welcome_text
from meute.core.config import KeysConfig


def test_welcome_text_uses_configured_keys() -> None:
    text = welcome_text(KeysConfig(focus_board="M-b", focus_main="C-o"))
    assert text == (
        "meute\n\nPick a session in the dashboard and press Enter.\nM-b: dashboard · C-o: main area"
    )
