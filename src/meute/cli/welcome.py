"""The welcome pane, shown in the main area while no session is displayed."""

import signal
from typing import NoReturn

from meute.core.config import KeysConfig


def welcome_text(keys: KeysConfig) -> str:
    """Return the text of the welcome pane, with the configured shortcuts."""
    return (
        "meute\n"
        "\n"
        "Pick a session in the dashboard and press Enter, or click it.\n"
        f"{keys.focus_board}: dashboard · {keys.focus_main}: main area\n"
        f"{keys.next_attention} / {keys.previous_attention}:"
        " next / previous session that needs attention\n"
        f"{keys.quick_task}: new task, from anywhere\n"
        f"{keys.detach} or q in the dashboard: detach, everything keeps running\n"
        "Hold Shift to select text with the mouse."
    )


def wait_forever() -> NoReturn:
    """Sleep until a signal ends the process: the pane must stay alive."""
    while True:
        signal.pause()
