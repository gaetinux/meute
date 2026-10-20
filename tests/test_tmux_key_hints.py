"""The status line shows the global keys, and the meute status where the board is hidden."""

from dataclasses import replace
from pathlib import Path

from meute.tmux.client import Tmux
from meute.tmux.conf import Keys, key_hints, render_config
from meute.tmux.layout import ensure_layout
from test_tmux_layout import SPEC
from tmux_support import TestServer

KEYS = Keys(focus_board="M-b", focus_main="M-o")
STATUS = "▶ alpha, beta · 1 need attention"  # a comma must not end the conditional


def test_hints_are_built_from_the_configured_keys() -> None:
    assert key_hints(KEYS) == "M-b panel · M-o back · M-n/M-N next · M-t task · M-q detach"


def test_hints_leave_out_the_keys_bound_to_meute_commands_when_there_are_none() -> None:
    assert key_hints(KEYS, with_commands=False) == "M-b panel · M-o back · M-q detach"


def _rendered(tmux: Tmux, session: str) -> str:
    return tmux.run(
        "display-message", "-p", "-t", f"={session}:", "#{E:status-left}|#{E:status-right}"
    )


def _start(server: TestServer, tmp_path: Path, threshold: int) -> Tmux:
    tmux = server.tmux
    spec = replace(SPEC, keys=KEYS, narrow_threshold=threshold, attention_command=("meute",))
    conf = tmp_path / "tmux.conf"
    _ = conf.write_text(render_config(spec))
    _ = tmux.run("source-file", str(conf))
    _ = tmux.run("set-option", "-g", "@meute_status", STATUS)
    _ = ensure_layout(tmux, spec)
    return tmux


def test_beside_the_board_the_line_shows_only_the_hints(
    tmux_server: TestServer, tmp_path: Path
) -> None:
    tmux = _start(tmux_server, tmp_path, threshold=120)
    rendered = _rendered(tmux, "meute")
    assert rendered.startswith("M-b panel · M-o back · M-n/M-N next · M-t task · M-q detach")
    assert STATUS not in rendered


def test_in_narrow_mode_the_line_adds_the_meute_status(
    tmux_server: TestServer, tmp_path: Path
) -> None:
    tmux = _start(tmux_server, tmp_path, threshold=300)
    rendered = _rendered(tmux, "meute")
    assert "M-b panel" in rendered
    assert STATUS in rendered


def test_a_session_shown_full_screen_adds_the_meute_status(
    tmux_server: TestServer, tmp_path: Path
) -> None:
    tmux = _start(tmux_server, tmp_path, threshold=120)
    _ = tmux.run("new-session", "-d", "-s", "meute-bg", "sh", "-c", "sleep 3600")
    rendered = _rendered(tmux, "meute-bg")
    assert "M-b panel" in rendered
    assert STATUS in rendered
