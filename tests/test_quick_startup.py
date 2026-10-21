"""The `M-t` window starts without checking tmux or rewriting its configuration."""

import pytest

from meute.cli.context import CliContext
from meute.cli.task_quick import CliQuickBackend
from meute.cli.task_quick_create import create_quick_task
from meute.cli.tmux_env import DEFAULT_SOCKET, meute_tmux
from meute.core.db.projects import create_project
from meute.core.errors import InvalidInput
from meute.core.project import ProjectRef
from test_cli_task_quick import ctx  # noqa: F401 — fixture reused  # pyright: ignore[reportUnusedImport] — fixture reused


def test_meute_tmux_writes_nothing(ctx: CliContext) -> None:  # noqa: F811 — fixture
    config = ctx.paths.state_dir / "tmux.conf"
    tmux = meute_tmux(ctx, {"MEUTE_TMUX_SOCKET": "meute-test-x"})
    assert (tmux.socket, tmux.config_file) == ("meute-test-x", config)
    assert meute_tmux(ctx, {}).socket == DEFAULT_SOCKET
    assert not config.exists()


def test_the_backend_uses_the_projects_it_is_given(ctx: CliContext) -> None:  # noqa: F811 — fixture
    infra = create_project(ctx.db, "infra")
    given = (ProjectRef(id=infra.id, name="infra"),)
    _ = create_project(ctx.db, "later")
    assert CliQuickBackend(ctx, None, given).context().projects == given


def test_quick_creation_resolves_against_the_given_projects(ctx: CliContext) -> None:  # noqa: F811 — fixture
    infra = create_project(ctx.db, "infra")
    ref = ProjectRef(id=infra.id, name="infra")
    assert create_quick_task(ctx, "Fix @infra", None, (ref,)).project == ref
    with pytest.raises(InvalidInput, match=r"^unknown project: infra$"):
        _ = create_quick_task(ctx, "Fix @infra", None, ())
