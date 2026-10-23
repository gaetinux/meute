"""A long-lived context (the board) composes each session with the instructions of the moment."""

from pathlib import Path

import pytest

from meute.cli.context import CliContext
from meute.cli.session_context import session_context
from meute.core.actor import Actor, Author, Channel
from meute.core.config import load_config
from meute.core.context import CONTRADICTION_RULE
from meute.core.db.connection import Database
from meute.core.errors import ConfigError
from meute.core.paths import Paths
from support import FIXED


def _context(root: Path, db: Database) -> CliContext:
    paths = Paths.from_env(
        {
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_STATE_HOME": str(root / "state"),
        },
        home=root / "home",
    )
    paths.config_file.parent.mkdir(parents=True)
    paths.config_file.write_text('[claude]\ninstructions = "first"\n', encoding="utf-8")
    return CliContext(
        db=db,
        now=FIXED,
        actor=Actor(author=Author.USER, channel=Channel.CLI),
        config=load_config(paths.config_file),
        paths=paths,
    )


def test_the_next_context_reads_the_instructions_written_since(
    tmp_path: Path, db: Database
) -> None:
    ctx = _context(tmp_path, db)
    assert session_context(ctx, project_id=None, repo_id=None, task_id=None) == (
        f"{CONTRADICTION_RULE}\n\nGlobal instructions:\nfirst"
    )
    ctx.paths.config_file.write_text('[claude]\ninstructions = "second"\n', encoding="utf-8")
    assert session_context(ctx, project_id=None, repo_id=None, task_id=None) == (
        f"{CONTRADICTION_RULE}\n\nGlobal instructions:\nsecond"
    )


def test_a_configuration_broken_since_is_a_meute_error(tmp_path: Path, db: Database) -> None:
    ctx = _context(tmp_path, db)
    ctx.paths.config_file.write_text("[claude\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        _ = session_context(ctx, project_id=None, repo_id=None, task_id=None)
