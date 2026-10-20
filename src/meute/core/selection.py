"""Keeping the selected line of a list across refreshes, by the keys of its lines."""

from collections.abc import Sequence


def keep_selected(
    keys: Sequence[str | None], old_key: str | None, fallback: int, *, old_group: str | None
) -> int:
    """Return the index to select among lines whose keys are `keys` (None: not selectable).

    The line with `old_key` wins, else the heading `group:{old_group}` (its group was folded),
    else the `fallback`-th selectable line, `fallback` clamped to them. Returns -1 when no line
    is selectable.
    """
    choices = [index for index, key in enumerate(keys) if key is not None]
    if not choices:
        return -1
    for wanted in (old_key, None if old_group is None else f"group:{old_group}"):
        if wanted is not None:
            found = next((index for index in choices if keys[index] == wanted), None)
            if found is not None:
                return found
    return choices[min(max(fallback, 0), len(choices) - 1)]
