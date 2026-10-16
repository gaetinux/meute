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


def test_foreign_imports_allow_stdlib_and_own_meute_packages() -> None:
    source = "import os\nfrom meute.core import x\nimport meute.core.y\nfrom . import z\n"
    assert guards.foreign_imports(source, ("core",)) == []


def test_foreign_imports_report_third_party_and_other_meute_packages() -> None:
    source = "import typer\nimport meute.claude\nfrom meute.ingest.x import y\n"
    assert guards.foreign_imports(source, ("core",)) == ["typer", "meute.claude", "meute.ingest.x"]


def test_foreign_imports_report_from_meute_import_subpackage() -> None:
    assert guards.foreign_imports("from meute import tmux\n", ("core",)) == ["meute.tmux"]
    assert guards.foreign_imports("import meute\n", ("core",)) == ["meute"]


def test_foreign_imports_do_not_confuse_prefix_siblings() -> None:
    assert guards.foreign_imports("import meute.core_extra\n", ("core",)) == ["meute.core_extra"]


def test_pyright_mode_lowering_directives_are_always_reported() -> None:
    for directive in ("basic", "standard", "off"):
        source = f"# pyright: {directive} — because\nx = 1\n"
        assert guards.suppressions_without_reason(source) == [1], directive


def test_pyright_rule_override_without_reason_is_reported() -> None:
    assert guards.suppressions_without_reason("# pyright: reportAny=false\n") == [1]


def test_pyright_rule_override_with_reason_is_allowed() -> None:
    assert guards.suppressions_without_reason("# pyright: reportAny=false — raw JSON\n") == []


def test_pyright_strict_is_allowed() -> None:
    assert guards.suppressions_without_reason("# pyright: strict\n") == []
    assert guards.suppressions_without_reason("#pyright:   strict  \n") == []


def test_pyright_strict_with_rule_override_is_reported() -> None:
    assert guards.suppressions_without_reason("# pyright: strict, reportAny=false\n") == [1]
    assert guards.suppressions_without_reason("# pyright: strictListInference=false\n") == [1]
    assert guards.suppressions_without_reason("# pyright: strict, reportAny=false — raw\n") == []


def test_file_level_ruff_noqa_without_reason_is_reported() -> None:
    assert guards.suppressions_without_reason("# ruff: noqa: E501\n") == [1]


def test_file_level_ruff_noqa_with_reason_is_allowed() -> None:
    assert guards.suppressions_without_reason("# ruff: noqa: E501 — generated\n") == []


def test_uppercase_noqa_is_reported() -> None:
    assert guards.suppressions_without_reason("x = 1  # NOQA: E501\n") == [1]


def test_noqa_after_another_comment_is_reported() -> None:
    assert guards.suppressions_without_reason("x = 1  # see docs  # noqa: E501\n") == [1]


def test_type_ignore_without_reason_is_reported() -> None:
    assert guards.suppressions_without_reason("x = 1  # type: ignore[assignment]\n") == [1]
