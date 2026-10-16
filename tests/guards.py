"""Static checks shared by the guard tests: pure functions over source text."""

import ast
import io
import re
import sys
import tokenize

STDLIB_ONLY_PACKAGES: tuple[str, ...] = ("core", "tmux", "git", "ingest")

_SUPPRESSION = re.compile(r"#\s*(?:noqa|pyright:\s*ignore|type:\s*ignore)\b")
_REASON_SEPARATOR = " — "


def _is_assert_never(statement: ast.stmt) -> bool:
    if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)):
        return False
    func = statement.value.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return name == "assert_never"


def wildcard_cases(source: str) -> list[int]:
    """Return the lines of `case _:` arms that do not end the match with assert_never."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.match_case) or node.guard is not None:
            continue
        pattern = node.pattern
        is_wildcard = isinstance(pattern, ast.MatchAs) and pattern.pattern is None
        if is_wildcard and not (len(node.body) == 1 and _is_assert_never(node.body[0])):
            lines.append(pattern.lineno)
    return sorted(lines)


def suppressions_without_reason(source: str) -> list[int]:
    """Return the lines whose noqa / pyright: ignore comment lacks a ` — reason`."""
    lines: list[int] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT or not _SUPPRESSION.match(token.string):
            continue
        _, separator, reason = token.string.partition(_REASON_SEPARATOR)
        if not (separator and reason.strip()):
            lines.append(token.start[0])
    return lines


def non_stdlib_imports(source: str) -> list[str]:
    """Return the unique top-level third-party modules imported by `source`."""
    allowed = set(sys.stdlib_module_names) | {"meute"}
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            if root not in allowed and root not in found:
                found.append(root)
    return found
