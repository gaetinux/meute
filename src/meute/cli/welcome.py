"""The welcome pane, shown in the main area while no session is displayed."""

import signal
from typing import NoReturn

from meute.core.config import KeysConfig


def welcome_text(keys: KeysConfig) -> str:
    """Return the text of the welcome pane, with the configured shortcuts."""
    return (
        "meute\n"
        "\n"
        "Pick a session in the dashboard and press Enter.\n"
        f"{keys.focus_board}: dashboard · {keys.focus_main}: main area"
    )


def wait_forever() -> NoReturn:
    """Sleep until a signal ends the process: the pane must stay alive."""
    while True:
        signal.pause()
