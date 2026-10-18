"""Quoting of text that tmux would otherwise expand as a format."""


def format_literal(text: str) -> str:
    """Return `text` as a tmux format that expands to `text` itself.

    tmux expands `#{...}`, `#(shell)` and `#H`-style formats in `-c` paths and in
    `run-shell` commands; doubling every `#` keeps them literal.
    """
    return text.replace("#", "##")
