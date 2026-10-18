"""The text of meute's tmux status line."""

from meute.core.text import printable


def status_text(displayed: str | None, attention: int, five_hour_pct: float | None) -> str:
    """Return the status line: the displayed session, the attention count and the 5 h quota.

    Each part is left out when it has nothing to say, so the text may be empty.
    """
    parts: list[str] = []
    if displayed is not None:
        parts.append(f"▶ {displayed}")
    if attention > 0:
        parts.append(f"{attention} need attention")
    if five_hour_pct is not None:
        parts.append(f"5h {five_hour_pct:.0f}%")
    return printable(" · ".join(parts))
