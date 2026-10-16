#!/usr/bin/env bash
# PostToolUse hook: format the edited Rust file, then run `cargo check`.
# Exit 2 (errors on stderr) makes Claude see compilation errors immediately.
set -uo pipefail

input="$(cat)"
file="$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path") or "")
except Exception:
    print("")')"

case "$file" in
    *.rs) ;;
    *) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

[ -f "$file" ] && rustfmt --edition 2024 "$file" >/dev/null 2>&1

if output="$(cargo check --workspace --all-targets --message-format=short 2>&1)"; then
    exit 0
fi

{
    echo "cargo check a échoué :"
    printf '%s\n' "$output" | head -n 60
} >&2
exit 2
