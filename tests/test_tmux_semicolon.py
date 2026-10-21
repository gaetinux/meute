"""tmux takes an argument ending in `;` as a separator: every word must reach it literally."""

import json
import sys
from pathlib import Path

import pytest

from meute.tmux.client import literal_word
from meute.tmux.panes import Spawn, spawn_window
from support import wait_until
from tmux_support import TestServer

# Checked on tmux 3.5a: each of these words, once escaped, reaches the program unchanged.
_WORDS = ("a;", "a\\;", "a\\\\;", "a;;", ";", "\\;", "x;y", "a ;", "#{pane_id};", "b", "a\\")
_RECORD = (
    "import json, os, sys; open(sys.argv[1], 'w').write(json.dumps([os.getcwd(), *sys.argv[2:]]))"
)


@pytest.mark.parametrize("word", ["a;", "a\\;", ";"])
def test_a_final_semicolon_is_escaped(word: str) -> None:
    assert literal_word(word) == f"{word[:-1]}\\;"


@pytest.mark.parametrize("word", ["b", "x;y", "a\\", ""])
def test_other_words_are_unchanged(word: str) -> None:
    assert literal_word(word) == word


def test_the_program_gets_its_words_and_folder_unchanged(
    tmux_server: TestServer, tmp_path: Path
) -> None:
    folder = tmp_path / "repo;"
    folder.mkdir()
    out = tmp_path / "argv.json"
    command = (sys.executable, "-c", _RECORD, str(out), *_WORDS)
    _ = spawn_window(tmux_server.tmux, Spawn(session="semi", cwd=folder, command=command))
    wait_until("the program to run", out.exists)
    wait_until("its words", lambda: out.read_text(encoding="utf-8") != "")
    assert json.loads(out.read_text(encoding="utf-8")) == [str(folder), *_WORDS]


def test_a_message_ending_in_a_semicolon_is_kept(tmux_server: TestServer) -> None:
    assert tmux_server.tmux.run("display-message", "-p", "done;") == "done;"
