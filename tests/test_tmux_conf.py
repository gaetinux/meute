from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from meute.tmux.conf import Keys, LayoutSpec, _sh_quote, _tmux_escape, render_config  # pyright: ignore[reportPrivateUsage] — the quoting helpers are tested directly
from tmux_support import TestServer

SLEEP = ("sh", "-c", "sleep 3600")


def make_spec(
    sync: tuple[str, ...], attention: tuple[str, ...] = ("/opt/meute/bin/python", "-m", "meute")
) -> LayoutSpec:
    return LayoutSpec(
        board_width=60,
        narrow_threshold=120,
        board_command=SLEEP,
        welcome_command=SLEEP,
        sync_command=sync,
        attention_command=attention,
        keys=Keys(focus_board="M-p", focus_main="M-o"),
    )


def test_generated_config(snapshot: SnapshotAssertion) -> None:
    spec = make_spec(("/opt/meute/bin/python", "-m", "meute", "layout", "sync"))
    assert render_config(spec) == snapshot


def test_shell_quoting() -> None:
    assert _sh_quote("a b") == "'a b'"
    assert _sh_quote("l'appli") == r"'l'\''appli'"
    assert _sh_quote("") == "''"
    assert _tmux_escape('a\\b"c$d') == r"a\\b\"c\$d"


def test_generated_config_is_accepted_by_tmux(tmux_server: TestServer, tmp_path: Path) -> None:
    tmux = tmux_server.tmux
    conf = tmp_path / "tmux.conf"
    conf.write_text(render_config(make_spec(("/opt/my app/l'appli/python", "-m", "meute"))))
    tmux.run("source-file", str(conf))
    keys = tmux.run("list-keys", "-T", "root")
    assert "M-p" in keys
    assert "M-o" in keys
    hooks = tmux.run("show-hooks", "-g")
    assert "client-attached" in hooks
    assert "client-resized" in hooks


def test_attention_bindings_are_omitted_without_a_command() -> None:
    text = render_config(make_spec(("meute",), attention=()))
    assert "M-n" not in text
    assert "M-N" not in text
    assert "bind -n M-q detach-client" in text


def test_interface_is_installed_in_tmux(tmux_server: TestServer, tmp_path: Path) -> None:
    tmux = tmux_server.tmux
    conf = tmp_path / "tmux.conf"
    conf.write_text(render_config(make_spec(("meute",), attention=("/opt/my app/l'x/python",))))
    tmux.run("source-file", str(conf))
    keys = tmux.run("list-keys", "-T", "root")
    for key in ("M-n", "M-N", "M-q"):
        assert f" {key} " in keys
    assert tmux.run("show-options", "-g", "mouse").strip() == "mouse on"
