#!/usr/bin/env bash
# Tests for the Claude Code hooks. Runs every case in a temporary copy of the fixture.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hooks="$(cd "$here/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

proj="$work/proj"
mkdir -p "$proj" "$work/fakebin"
cp -r "$here/fixtures/." "$proj/"
printf 'target\n' > "$proj/.gitignore"
(
    cd "$proj" || exit 1
    git init -q
    git -c user.name=t -c user.email=t@t add -A
    git -c user.name=t -c user.email=t@t commit -qm init
) || { echo "fixture setup failed" >&2; exit 1; }

# Fake cargo: records that it was invoked.
cat > "$work/fakebin/cargo" <<FAKE
#!/usr/bin/env bash
touch "$work/witness"
exit 0
FAKE
chmod +x "$work/fakebin/cargo"

failures=0
out="" err="" code=0

reset_tree() {
    (cd "$proj" && git checkout -q -- . && git clean -fdq -e target)
    rm -f "$work/witness"
}

# run_hook <script> <stdin-json> [extra PATH prefix]
run_hook() {
    local script="$1" input="$2" prefix="${3:-}"
    local errfile="$work/stderr"
    out="$(cd "$work" && printf '%s' "$input" \
        | PATH="${prefix:+$prefix:}$PATH" CLAUDE_PROJECT_DIR="$proj" bash "$hooks/$script" 2>"$errfile")"
    code=$?
    err="$(cat "$errfile")"
}

report() {
    local name="$1" ok="$2"
    if [ "$ok" = 1 ]; then
        echo "OK $name"
    else
        echo "ÉCHEC $name (code=$code stderr=${err:0:200})"
        failures=$((failures + 1))
    fi
}

case_non_rust_ignored() {
    reset_tree
    run_hook rust-check.sh '{"tool_input":{"file_path":"README.md"}}'
    [ "$code" = 0 ] && [ -z "$err" ] && [ -z "$out" ] && return 0
    return 1
}

case_rust_ok() {
    reset_tree
    run_hook rust-check.sh "{\"tool_input\":{\"file_path\":\"$proj/src/lib.rs\"}}"
    [ "$code" = 0 ]
}

case_rust_error_blocks() {
    reset_tree
    printf 'fn x() -> u8 { "a" }\n' > "$proj/src/lib.rs"
    run_hook rust-check.sh "{\"tool_input\":{\"file_path\":\"$proj/src/lib.rs\"}}"
    [ "$code" = 2 ] && [[ "$err" == *"cargo check a échoué"* ]] && [[ "$err" == *"mismatched types"* ]]
}

case_verify_clean_tree() {
    reset_tree
    run_hook verify.sh '{"stop_hook_active":false}' "$work/fakebin"
    [ "$code" = 0 ] && [ ! -e "$work/witness" ]
}

add_failing_test() {
    cat >> "$proj/src/lib.rs" <<'RS'

#[cfg(test)]
mod tests {
    #[test]
    fn fails() {
        assert_eq!(super::one(), 2);
    }
}
RS
}

case_verify_failing_blocks() {
    reset_tree
    add_failing_test
    run_hook verify.sh '{"stop_hook_active":false}'
    [ "$code" = 2 ] && [[ "$err" == *"corrige avant de terminer"* ]]
}

case_verify_loop_guard() {
    reset_tree
    add_failing_test
    run_hook verify.sh '{"stop_hook_active":true}'
    [ "$code" = 0 ] && [[ "$err" == *"signale-le explicitement"* ]]
}

for c in non_rust_ignored rust_ok rust_error_blocks verify_clean_tree verify_failing_blocks verify_loop_guard; do
    if "case_$c"; then report "$c" 1; else report "$c" 0; fi
done

exit $((failures > 0 ? 1 : 0))
