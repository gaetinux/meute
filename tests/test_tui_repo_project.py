"""`@name` naming a known repository in the TUI: the quick window, `a` and `@` of the Tasks tab."""

from dataclasses import replace

from textual.pilot import Pilot

from meute.core.board_view import CreateTask, MoveToRepoProject
from meute.core.task import TaskId
from meute.tui.board import BoardApp
from meute.tui.quick_task import QuickContext, QuickTaskApp
from support import board_repo
from test_tui_quick_task import (
    _ME as _QUICK_ME,  # pyright: ignore[reportPrivateUsage] — quick window test helper
)
from test_tui_quick_task import (
    FakeQuickBackend,
    _plain,  # pyright: ignore[reportPrivateUsage] — quick window test helper
)
from test_tui_quick_task import (
    _run as _run_quick,  # pyright: ignore[reportPrivateUsage] — quick window test helper
)
from test_tui_quick_task import (
    _type as _type_quick,  # pyright: ignore[reportPrivateUsage] — quick window test helper
)
from test_tui_task_edit import (  # the helpers of the edit tests
    _ME,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _VERSION,  # pyright: ignore[reportPrivateUsage] — edit test helper
    EditBackend,
    _data,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _line,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _run,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _text,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _type,  # pyright: ignore[reportPrivateUsage] — edit test helper
)

_NEW = "poc-app-rust  (new project from repository)"


class RepoQuickBackend(FakeQuickBackend):
    """The fake quick backend, with one known repository."""

    def context(self) -> QuickContext:
        return replace(super().context(), repo_names=("poc-app-rust",))


def _with_repo() -> EditBackend:
    return EditBackend(replace(_data(), repos=(board_repo(1, "poc-app-rust", None),)))


def test_the_quick_window_previews_and_creates_a_repository_project() -> None:
    backend = RepoQuickBackend(default=_QUICK_ME)
    app = QuickTaskApp(backend)

    async def scenario(pilot: Pilot[None]) -> None:
        await _type_quick(pilot, "Fix CI @poc-app-rust")
        assert _NEW in _plain(app, "#input-preview")
        await pilot.press("enter")
        await pilot.pause()

    _run_quick(app, scenario)
    assert backend.created == ["Fix CI @poc-app-rust"]


def test_a_previews_and_creates_a_repository_project() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("a")
        await _type(pilot, "Fix CI @poc-app-rust")
        assert _NEW in _text(app, "input-preview")
        await pilot.press("enter")

    actions = _run(steps, _with_repo()).actions
    assert actions == [CreateTask(text="Fix CI @poc-app-rust", project=_ME)]


def test_at_moves_the_task_to_a_new_repository_project() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("at")
        _line(app).value = "POC-app-rust"
        await pilot.press("enter")

    assert _run(steps, _with_repo()).actions == [
        MoveToRepoProject(task_id=TaskId(1), version=_VERSION, name="poc-app-rust")
    ]


def test_at_suggests_a_repository_name() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("at")
        _line(app).value = "poc-app-rst"
        await pilot.press("enter")
        assert _text(app, "footer") == "Error: unknown project: poc-app-rst (poc-app-rust?)"

    assert _run(steps, _with_repo()).actions == []
