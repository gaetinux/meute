#!/usr/bin/env bash
# PostToolUse hook: format the edited Python file, then lint and type-check it.
# Exit 2 (errors on stderr) makes Claude see lint and type errors immediately.
set -uo pipefail

input="$(cat)"
file="$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path") or "")
except Exception:
    print("")')"

case "$file" in
    *.py) ;;
    *) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
root="$(realpath -- .)" || exit 0

# Only existing files inside the project are checked (resolved paths, symlinks followed).
file="$(realpath -e -- "$file" 2>/dev/null)" || exit 0
case "$file" in
    "$root"/*) ;;
    *) exit 0 ;;
esac

if ! command -v uv >/dev/null 2>&1; then
    echo "uv introuvable : vérification Python ignorée" >&2
    exit 0
fi

uv run --frozen ruff format -q -- "$file" >/dev/null 2>&1

# basedpyright rejects `--`; the resolved path is absolute, so it cannot look like an option.
lint_out="$(uv run --frozen ruff check --fix -q -- "$file" 2>&1)"
lint=$?
type_out="$(uv run --frozen basedpyright "$file" 2>&1)"
types=$?

[ "$lint" = 0 ] && [ "$types" = 0 ] && exit 0

{
    echo "vérification Python en échec :"
    printf '%s\n%s\n' "$lint_out" "$type_out" | head -n 60
} >&2
exit 2
