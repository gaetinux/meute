"""The texts that say why a session cannot be resumed, shared by the board and the CLI."""

NOT_CLAUDE = "only Claude sessions resume"


def still_running_text(title: str) -> str:
    """Return the refusal for a session whose process still runs; `title` is shown as given."""
    return f'"{title}" is still running'


def no_native_id_text(title: str) -> str:
    """Return the refusal for a session whose Claude id was never confirmed."""
    return f'"{title}" cannot be resumed: Claude never confirmed its id'
