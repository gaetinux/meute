"""In narrow mode (zoomed window) `M-o` must not unzoom."""

import shlex

from conftest import Sandbox


def _zoomed(sandbox: Sandbox) -> str:
    return (
        sandbox.tmux()
        .run("display-message", "-p", "-t", "=meute:main", "#{window_zoomed_flag}")
        .strip()
    )


def _run_binding(sandbox: Sandbox) -> None:
    keys = sandbox.tmux().run("list-keys", "-T", "root", "M-o")
    command = keys.split(" M-o ", 1)[1].replace("if-shell", "if-shell -t =meute:main", 1)
    _ = sandbox.tmux().run(*shlex.split(command))  # no client here: aim at the window


def test_focus_main_leaves_the_narrow_window_zoomed(sandbox: Sandbox) -> None:
    assert sandbox.run("layout", "sync").returncode == 0
    _ = sandbox.tmux().run("resize-window", "-t", "=meute:main", "-x", "100")
    assert sandbox.run("layout", "sync").returncode == 0
    assert _zoomed(sandbox) == "1"
    _run_binding(sandbox)
    assert _zoomed(sandbox) == "1"


def test_focus_main_binding_does_nothing_when_zoomed(sandbox: Sandbox) -> None:
    assert sandbox.run("layout", "sync").returncode == 0
    keys = sandbox.tmux().run("list-keys", "-T", "root", "M-o")
    assert 'if-shell -F "#{window_zoomed_flag}"' in keys
