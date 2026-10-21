"""`@name` of a quick entry naming a known repository rather than a project."""

from meute.core.project import ProjectId, ProjectRef
from meute.core.quick_preview import (
    Named,
    NewFromRepo,
    UnknownProject,
    choice_project_id,
    preview_lines,
    quick_preview,
    resolve_quick_project,
)
from meute.core.styled import Role, plain
from support import NOW

INFRA = ProjectRef(id=ProjectId(1), name="infra")
REPOS = ("poc-app-rust", "dotfiles")


def test_a_repository_name_creates_its_project() -> None:
    choice = resolve_quick_project(" POC-app-rust ", None, [INFRA], REPOS)
    assert choice == NewFromRepo("poc-app-rust")
    assert choice_project_id(choice) == NewFromRepo("poc-app-rust")


def test_a_project_wins_over_a_repository_of_the_same_name() -> None:
    assert resolve_quick_project("infra", None, [INFRA], ("Infra",)) == Named(INFRA)


def test_the_suggestion_looks_among_projects_and_repositories() -> None:
    choice = resolve_quick_project("dotfils", None, [INFRA], REPOS)
    assert choice == UnknownProject(name="dotfils", suggestion="dotfiles")


def test_the_preview_says_the_project_is_new_and_can_create() -> None:
    preview = quick_preview(
        "Fix CI @poc-app-rust", now=NOW, default=None, projects=[INFRA], repo_names=REPOS
    )
    assert preview.project == NewFromRepo("poc-app-rust")
    assert preview.error is None
    assert preview.can_create
    lines = preview_lines(preview, NOW)
    assert [plain(line) for line in lines] == [
        "Title     Fix CI",
        "Project   poc-app-rust  (new project from repository)",
        "Enter create · Esc cancel",
    ]
    assert [span.role for span in lines[1][1:]] == [Role.KIND, Role.DIM]


def test_the_new_project_name_is_printable() -> None:
    preview = quick_preview("x @a\x1bb", now=NOW, default=None, projects=[], repo_names=["a\x1bb"])
    assert preview.project == NewFromRepo("a\x1bb")
    assert all("\x1b" not in plain(line) for line in preview_lines(preview, NOW))
