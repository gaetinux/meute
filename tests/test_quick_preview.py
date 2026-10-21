from hypothesis import given
from hypothesis import strategies as st

from meute.core.project import ProjectId, ProjectRef
from meute.core.quick_preview import (
    Displayed,
    Floating,
    Named,
    UnknownProject,
    preview_lines,
    quick_preview,
    resolve_quick_project,
)
from meute.core.status import Priority
from meute.core.styled import Role, plain
from meute.core.views import format_due
from support import NOW

INFRA = ProjectRef(id=ProjectId(1), name="infra")
MODS = ProjectRef(id=ProjectId(2), name="mods")
MEUTE = ProjectRef(id=ProjectId(3), name="meute")
ALL = [INFRA, MODS, MEUTE]


def _texts(text: str, default: ProjectRef | None = MEUTE) -> list[str]:
    preview = quick_preview(text, now=NOW, default=default, projects=ALL)
    return [plain(line) for line in preview_lines(preview, NOW)]


def test_mockup_with_displayed_project() -> None:
    preview = quick_preview("Relire la PR #11 !! >tomorrow", now=NOW, default=MEUTE, projects=ALL)
    assert preview.title == "Relire la PR #11"
    assert preview.project == Displayed(MEUTE)
    assert preview.priority is Priority.URGENT
    assert preview.error is None
    assert preview.can_create
    assert preview.due is not None
    assert format_due(preview.due, NOW) == "tomorrow"
    assert _texts("Relire la PR #11 !! >tomorrow") == [
        "Title     Relire la PR #11",
        "Project   meute  (displayed session · @none: floating)",
        "Priority  urgent",
        "Due       tomorrow",
        "Enter create · Esc cancel",
    ]


def test_unknown_project_suggests_close_name() -> None:
    preview = quick_preview(
        "Appeler le support @infar >tonight", now=NOW, default=None, projects=[INFRA, MODS]
    )
    assert preview.project == UnknownProject(name="infar", suggestion="infra")
    assert preview.error == "unknown project"
    assert not preview.can_create
    lines = _texts("Appeler le support @infar >tonight", None)
    assert lines[1] == "Project   @infar: unknown project (infra?)"
    assert lines[-1] == "Cannot create: fix the project or use @none · Esc cancel"


def test_unknown_project_without_suggestion() -> None:
    preview = quick_preview("x @zzzzzz", now=NOW, default=None, projects=ALL)
    assert preview.project == UnknownProject(name="zzzzzz", suggestion=None)
    assert _texts("x @zzzzzz")[1] == "Project   @zzzzzz: unknown project"


def test_none_is_floating_without_case() -> None:
    for word in ("@none", "@NONE"):
        preview = quick_preview(f"x {word}", now=NOW, default=MEUTE, projects=ALL)
        assert preview.project == Floating(explicit=True)
    assert _texts("x @none")[1] == "Project   floating"


def test_name_matches_without_case() -> None:
    preview = quick_preview("x @INFRA", now=NOW, default=None, projects=ALL)
    assert preview.project == Named(INFRA)
    assert _texts("x @INFRA")[1] == "Project   infra"


def test_no_project_and_no_default_is_floating_implicit() -> None:
    preview = quick_preview("x", now=NOW, default=None, projects=ALL)
    assert preview.project == Floating(explicit=False)
    assert _texts("x", None)[1] == "Project   floating  (no displayed session)"


def test_unrecognised_due_token_stays_in_title() -> None:
    preview = quick_preview("Call >bientôt", now=NOW, default=None, projects=ALL)
    assert preview.title == "Call >bientôt"
    assert preview.due is None
    assert not any(line.startswith("Due") for line in _texts("Call >bientôt"))


def test_empty_text_has_no_error_and_cannot_create() -> None:
    preview = quick_preview("   ", now=NOW, default=MEUTE, projects=ALL)
    assert preview.title is None
    assert preview.error is None
    assert not preview.can_create
    assert _texts("  ")[-1] == "Cannot create: empty title · Esc cancel"


def test_only_attributes_is_empty_title_error() -> None:
    preview = quick_preview("@infra !", now=NOW, default=None, projects=ALL)
    assert preview.title is None
    assert preview.error == "empty title"
    assert _texts("@infra !")[-1] == "Cannot create: empty title · Esc cancel"


def test_roles() -> None:
    def roles(text: str) -> dict[str, Role]:
        preview = quick_preview(text, now=NOW, default=MEUTE, projects=ALL)
        return {
            line[0].text.strip(): line[1].role
            for line in preview_lines(preview, NOW)
            if len(line) > 1
        }

    assert roles("x ! @nope")["Priority"] is Role.WARN
    assert roles("x !! @nope")["Priority"] is Role.HIGH
    assert roles("x @nope")["Title"] is Role.TITLE
    assert roles("x @nope")["Project"] is Role.HIGH
    assert roles("x")["Project"] is Role.KIND


def test_normal_priority_is_omitted() -> None:
    assert not any(line.startswith("Priority") for line in _texts("x"))


def test_control_characters_are_neutralised() -> None:
    lines = _texts("bad\x1b[31m @a\x1bb")
    assert all("\x1b" not in line for line in lines)


def test_resolve_matches_preview() -> None:
    assert resolve_quick_project(None, MEUTE, ALL) == Displayed(MEUTE)
    assert resolve_quick_project("Mods", None, ALL) == Named(MODS)


@given(st.text(), st.sampled_from([None, MEUTE]), st.lists(st.sampled_from(ALL), unique=True))
def test_preview_never_raises(
    text: str, default: ProjectRef | None, projects: list[ProjectRef]
) -> None:
    preview = quick_preview(text, now=NOW, default=default, projects=projects)
    for line in preview_lines(preview, NOW):
        assert "\n" not in plain(line)
