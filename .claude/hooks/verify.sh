#!/usr/bin/env bash
# Stop / SubagentStop hook: when Rust or Cargo files changed, require clippy and tests to pass.
# Exit 2 prevents the agent from declaring itself done.
set -uo pipefail

input="$(cat)"
active="$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    print("true" if json.load(sys.stdin).get("stop_hook_active") is True else "false")
except Exception:
    print("false")')"

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

if [ -z "$(git status --porcelain -- '*.rs' 'Cargo.toml' '*/Cargo.toml' 'Cargo.lock')" ]; then
    exit 0
fi

if output="$(
    { cargo clippy --workspace --all-targets -- -D warnings \
        && cargo nextest run --workspace --failure-output final --hide-progress-bar; } 2>&1
)"; then
    exit 0
fi

if [ "$active" = "true" ]; then
    echo "vérification toujours en échec — signale-le explicitement dans ton rapport" >&2
    exit 0
fi

{
    echo "vérification en échec, corrige avant de terminer :"
    printf '%s\n' "$output" | tail -n 60
} >&2
exit 2
