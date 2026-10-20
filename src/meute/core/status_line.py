"""The text of meute's tmux status line."""

from meute.core.text import printable


def status_text(
    displayed: str | None, attention: int, five_hour_pct: float | None, overdue: int = 0
) -> str:
    """Return the status line: displayed session, attention count, 5 h quota, overdue tasks.

    Each part is left out when it has nothing to say, so the text may be empty. `#` is
    doubled: tmux would read `#[...]` in a title as a style when it expands the option.
    """
    parts: list[str] = []
    if displayed is not None:
        parts.append(f"▶ {displayed}")
    if attention > 0:
        parts.append(f"{attention} need attention")
    if five_hour_pct is not None:
        parts.append(f"5h {five_hour_pct:.0f}%")
    if overdue > 0:
        parts.append(f"{overdue} overdue")
    return printable(" · ".join(parts)).replace("#", "##")
