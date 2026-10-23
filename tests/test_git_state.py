"""Tests of the Git state parsers and its card text (outputs captured from real git, frozen)."""

import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st
from syrupy.assertion import SnapshotAssertion

from meute.core.git_state import GitState, git_text, parse_numstat, parse_status_v2

OID = "c9f07c9c6ee01c7a0e2a085e2b83478463cd2f49"
HEAD_LINES = f"# branch.oid {OID}\n# branch.head main\n"
UPSTREAM = "# branch.upstream origin/main\n"

INITIAL = "# branch.oid (initial)\n# branch.head main\n"
CLEAN_NO_UPSTREAM = HEAD_LINES
CLEAN = HEAD_LINES + UPSTREAM + "# branch.ab +0 -0\n"
MODIFIED = (
    HEAD_LINES
    + UPSTREAM
    + "# branch.ab +0 -0\n"
    + "1 .M N... 100644 100644 100644 ce013625030ba8dba906f756967f9e9ca394464a "
    + "ce013625030ba8dba906f756967f9e9ca394464a README.md\n"
    + "? new.txt\n"
)
UNTRACKED_ONLY = HEAD_LINES + UPSTREAM + "# branch.ab +0 -0\n? new.txt\n"
AHEAD = HEAD_LINES + UPSTREAM + "# branch.ab +2 -0\n"
AHEAD_BEHIND = HEAD_LINES + UPSTREAM + "# branch.ab +2 -1\n"
BEHIND = HEAD_LINES + UPSTREAM + "# branch.ab +0 -1\n"
NO_UPSTREAM_BRANCH = f"# branch.oid {OID}\n# branch.head feat/x\n"
DETACHED = f"# branch.oid {OID}\n# branch.head (detached)\n"
CONFLICT = (
    f"# branch.oid {OID}\n# branch.head b2\n"
    "1 A. N... 000000 100644 100644 0000000000000000000000000000000000000000 "
    "afdb230c84024991fc19bc450a5c6c2e2ec1af58 bin.dat\n"
    "u AA N... 000000 100644 100644 100644 0000000000000000000000000000000000000000 "
    "f719efd430d52bcfc8566a43b2eb655688d38871 5626abf0f72e58d7a153368ba57db4c673c0e171 k.txt\n"
)


def make(  # noqa: PLR0913 — a builder with a default for each field
    *,
    branch: str | None = "main",
    detached: str | None = None,
    upstream: bool = True,
    ahead: int = 0,
    behind: int = 0,
    dirty: bool = False,
    added: int = 0,
    removed: int = 0,
) -> GitState:
    return GitState(
        branch=branch,
        detached=detached,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        dirty=dirty,
        added=added,
        removed=removed,
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(INITIAL, make(upstream=False), id="initial"),
        pytest.param(CLEAN_NO_UPSTREAM, make(upstream=False), id="clean-no-upstream"),
        pytest.param(CLEAN, make(), id="clean"),
        pytest.param(MODIFIED, make(dirty=True), id="modified"),
        pytest.param(UNTRACKED_ONLY, make(dirty=True), id="untracked-only"),
        pytest.param(AHEAD, make(ahead=2), id="ahead"),
        pytest.param(AHEAD_BEHIND, make(ahead=2, behind=1), id="ahead-behind"),
        pytest.param(BEHIND, make(behind=1), id="behind"),
        pytest.param(NO_UPSTREAM_BRANCH, make(branch="feat/x", upstream=False), id="no-upstream"),
        pytest.param(
            DETACHED, make(branch=None, detached="c9f07c9", upstream=False), id="detached"
        ),
        pytest.param(CONFLICT, make(branch="b2", upstream=False, dirty=True), id="conflict"),
    ],
)
def test_parse_status_v2(text: str, expected: GitState) -> None:
    assert parse_status_v2(text) == expected


@pytest.mark.parametrize("text", ["", "\n", "garbage\n", "# branch.oid abc\n", "1 .M x\n"])
def test_parse_status_v2_without_head(text: str) -> None:
    assert parse_status_v2(text) is None


def test_parse_status_v2_ignores_malformed_ab() -> None:
    parsed = parse_status_v2(HEAD_LINES + UPSTREAM + "# branch.ab +x -y\n")
    assert parsed is not None
    assert (parsed.ahead, parsed.behind) == (0, 0)


def test_parse_status_v2_short_oid() -> None:
    parsed = parse_status_v2("# branch.oid abc\n# branch.head (detached)\n")
    assert parsed is not None
    assert parsed.detached == "abc"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", (0, 0)),
        ("1\t0\tREADME.md\n2\t0\tf.txt\n", (3, 0)),
        ("-\t-\tbin.dat\n1\t0\tf.txt\n", (1, 0)),
        ("10\t4\ta\n0\t7\tb\n", (10, 11)),
        ("x\t1\ta\nnot a line\n1\t2\n\n3\t4\tc\n", (3, 4)),
        ("1\t2\told => new\n", (1, 2)),
    ],
)
def test_parse_numstat(text: str, expected: tuple[int, int]) -> None:
    assert parse_numstat(text) == expected


CASES: dict[str, GitState] = {
    "clean": make(),
    "dirty": make(dirty=True),
    "full": make(ahead=2, behind=1, dirty=True, added=12, removed=3),
    "added-only": make(dirty=True, added=5),
    "ahead-only": make(ahead=3),
    "behind-only": make(behind=4),
    "not-pushed": make(branch="feat/x", upstream=False),
    "not-pushed-dirty": make(branch="feat/x", upstream=False, dirty=True, added=1, removed=2),
    "detached": make(branch=None, detached="a1b2c3d", upstream=False),
    "detached-dirty": make(branch=None, detached="a1b2c3d", upstream=False, dirty=True, added=1),
    "hostile": make(branch="bad\x1b[31m\nname"),
}


@pytest.mark.parametrize("name", list(CASES))
def test_git_text(name: str, snapshot: SnapshotAssertion) -> None:
    assert git_text(CASES[name]) == snapshot


def test_git_text_exact_card_example() -> None:
    assert git_text(CASES["full"]) == "main* +12 \u22123 \u21912 \u21931"


_texts = st.text(max_size=300)


@given(_texts)
def test_parsers_never_raise(text: str) -> None:
    parse_status_v2(text)
    parse_numstat(text)


_counts = st.integers(0, 10**6)
_states = st.builds(
    GitState,
    branch=st.one_of(st.none(), _texts),
    detached=st.one_of(st.none(), _texts),
    upstream=st.booleans(),
    ahead=_counts,
    behind=_counts,
    dirty=st.booleans(),
    added=_counts,
    removed=_counts,
)


@given(_states)
def test_git_text_is_one_safe_line(state: GitState) -> None:
    text = git_text(state)
    assert len(text.splitlines()) <= 1
    assert all(unicodedata.category(char) != "Cc" for char in text)


def test_huge_numbers_are_malformed() -> None:
    digits = "9" * 5000
    parsed = parse_status_v2(f"# branch.head main\n# branch.ab +{digits} -1\n")
    assert parsed is not None
    assert (parsed.ahead, parsed.behind) == (0, 0)
    assert parse_numstat(f"{digits}\t1\tf\n3\t4\tg\n") == (3, 4)


def test_detached_without_oid_shows_a_question_mark() -> None:
    parsed = parse_status_v2("# branch.head (detached)\n")
    assert parsed is not None
    assert parsed.detached == "?"
    assert git_text(parsed) == "(detached ?)"
