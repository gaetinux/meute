import guards

WILDCARD = "match x:\n    case A():\n        pass\n    case _:\n        pass\n"
EXHAUSTIVE = "match x:\n    case A():\n        pass\n    case _:\n        assert_never(x)\n"


def test_wildcard_case_is_reported_with_its_line() -> None:
    assert guards.wildcard_cases(WILDCARD) == [4]


def test_wildcard_case_ending_in_assert_never_is_allowed() -> None:
    assert guards.wildcard_cases(EXHAUSTIVE) == []


def test_suppression_without_reason_is_reported() -> None:
    assert guards.suppressions_without_reason("x = 1  # noqa: E501\n") == [1]


def test_suppression_with_reason_is_allowed() -> None:
    assert guards.suppressions_without_reason("x = 1  # noqa: E501 — long URL\n") == []


def test_bare_noqa_is_reported() -> None:
    assert guards.suppressions_without_reason("x = 1  # noqa\n") == [1]


def test_pyright_ignore_without_reason_is_reported() -> None:
    assert guards.suppressions_without_reason("x = 1  # pyright: ignore[reportAny]\n") == [1]


def test_pyright_ignore_with_reason_is_allowed() -> None:
    source = "x = 1  # pyright: ignore[reportAny] — json.loads\n"
    assert guards.suppressions_without_reason(source) == []


def test_empty_reason_is_reported() -> None:
    assert guards.suppressions_without_reason("x = 1  # noqa: E501 —  \n") == [1]


def test_non_stdlib_imports_ignores_stdlib_meute_and_relative() -> None:
    source = "import os\nimport typer\nfrom meute.core import x\nfrom . import y\n"
    assert guards.non_stdlib_imports(source) == ["typer"]
