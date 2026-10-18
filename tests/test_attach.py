"""`attach_command`: what the bare `meute` command runs to attach."""

from pathlib import Path

from meute.cli.attach import attach_command
from meute.cli.tmux_env import TmuxEnv
from meute.tmux.client import Tmux
from meute.tmux.conf import Keys, LayoutSpec

_SPEC = LayoutSpec(
    board_width=60,
    narrow_threshold=120,
    board_command=("true",),
    welcome_command=("true",),
    sync_command=("true",),
    keys=Keys(focus_board="M-p", focus_main="M-o"),
)
_CONF = Path("/state/meute/tmux.conf")
_ENV = TmuxEnv(tmux=Tmux(socket="meute-x", config_file=_CONF), spec=_SPEC, config_file=_CONF)


def test_attach_command_targets_main_window() -> None:
    args, _ = attach_command(_ENV, {})
    assert args == [
        "tmux",
        "-L",
        "meute-x",
        "-f",
        "/state/meute/tmux.conf",
        "attach-session",
        "-t",
        "=meute:main",
    ]


def test_attach_command_removes_tmux_variable() -> None:
    _, environ = attach_command(_ENV, {"TMUX": "/run/tmux/default,1,0", "HOME": "/h"})
    assert environ == {"HOME": "/h"}
