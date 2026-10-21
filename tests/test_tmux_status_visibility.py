"""The status line shows in every session, beside the dashboard too (§ 5.6)."""

from meute.tmux.client import Tmux
from meute.tmux.layout import ensure_layout
from test_tmux_layout import SPEC
from tmux_support import TestServer


def _status(tmux: Tmux, session: str) -> str:
    return tmux.run("display-message", "-p", "-t", f"={session}:", "#{status}").strip()


def test_status_line_shows_beside_the_dashboard(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    _ = ensure_layout(tmux, SPEC)
    assert _status(tmux, "meute") == "on"


def test_status_line_still_shows_in_other_sessions(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    _ = ensure_layout(tmux, SPEC)
    _ = tmux.run("new-session", "-d", "-s", "elsewhere", "sh", "-c", "sleep 3600")
    assert _status(tmux, "elsewhere") == "on"


def test_status_line_is_shown_again_after_a_repair(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    _ = ensure_layout(tmux, SPEC)
    _ = tmux.run("set-option", "-t", "=meute:", "status", "off")
    _ = ensure_layout(tmux, SPEC)
    assert _status(tmux, "meute") == "on"
