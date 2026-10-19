"""Writing the text of meute's tmux status line."""

from collections.abc import Sequence

from meute.core.attention import attention_count
from meute.core.session import Session
from meute.core.status_line import status_text
from meute.tmux.client import Tmux
from meute.tmux.names import STATUS_OPTION
from meute.tmux.panes import set_global_option


def publish_status(
    tmux: Tmux,
    displayed: str | None,
    sessions: Sequence[Session],
    five_hour_pct: float | None,
    last: str | None = None,
) -> str:
    """Write the status line unless its text equals `last`; return its text.

    Raises:
        TmuxError: tmux failed.
    """
    text = status_text(displayed, attention_count(sessions), five_hour_pct)
    if text != last:
        set_global_option(tmux, STATUS_OPTION, text)
    return text
