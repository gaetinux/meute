"""End-to-end tests of `meute layout sync` and of the bare `meute` command."""

from conftest import Sandbox

_FAILED = "meute: attaching to tmux failed\n"


def _roles(sandbox: Sandbox) -> list[tuple[str, str]]:
    """(role, start command) of every pane of `meute:main`."""
    output = sandbox.tmux().run(
        "list-panes", "-t", "=meute:main", "-F", "#{@meute_role}\t#{pane_start_command}"
    )
    rows: list[tuple[str, str]] = []
    for line in output.splitlines():
        role, _, command = line.partition("\t")
        rows.append((role, command))
    return rows


def test_layout_sync_creates_board_and_welcome(sandbox: Sandbox) -> None:
    result = sandbox.run("layout", "sync")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    roles = _roles(sandbox)
    assert sorted(role for role, _ in roles) == ["board", "welcome"]
    (board_command,) = (command for role, command in roles if role == "board")
    assert "-m meute board" in board_command


def test_layout_sync_is_idempotent(sandbox: Sandbox) -> None:
    assert sandbox.run("layout", "sync").returncode == 0
    before = sandbox.tmux().run("list-panes", "-a", "-F", "#{pane_id} #{@meute_role}")
    result = sandbox.run("layout", "sync")
    assert (result.returncode, result.stderr) == (0, "")
    assert sandbox.tmux().run("list-panes", "-a", "-F", "#{pane_id} #{@meute_role}") == before


def test_layout_sync_zooms_when_narrow(sandbox: Sandbox) -> None:
    assert sandbox.run("layout", "sync").returncode == 0
    sandbox.tmux().run("resize-window", "-t", "=meute:main", "-x", "100")
    assert sandbox.run("layout", "sync").returncode == 0
    zoomed = sandbox.tmux().run(
        "display-message", "-p", "-t", "=meute:main", "#{window_zoomed_flag}"
    )
    assert zoomed == "1"


def test_bare_meute_builds_layout_then_fails_to_attach_without_terminal(
    sandbox: Sandbox,
) -> None:
    result = sandbox.run(env={"TMUX": ""})
    assert result.returncode == 1
    assert result.stderr.endswith(_FAILED), result.stderr
    assert not result.stderr.startswith("Warning")
    assert sorted(role for role, _ in _roles(sandbox)) == ["board", "welcome"]


def test_bare_meute_inside_tmux_warns(sandbox: Sandbox) -> None:
    result = sandbox.run(env={"TMUX": "/run/tmux/default,1,0"})
    config = sandbox.root / "config" / "meute" / "config.toml"
    warning = (
        "Warning: meute opens inside your current tmux. If it already uses M-p or M-o,"
        f" change them in the [keys] section of {config}.\n"
    )
    assert result.returncode == 1
    assert result.stderr.startswith(warning), result.stderr
    assert result.stderr.endswith(_FAILED), result.stderr
