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
printf '.venv\n__pycache__\n.ruff_cache\n.pytest_cache\n' > "$proj/.gitignore"
(
    cd "$proj" || exit 1
    uv lock -q && uv sync -q || exit 1
    git init -q
    git -c user.name=t -c user.email=t@t add -A
    git -c user.name=t -c user.email=t@t commit -qm init
) || { echo "fixture setup failed" >&2; exit 1; }

# Fake uv: records that it was invoked.
cat > "$work/fakebin/uv" <<FAKE
#!/usr/bin/env bash
touch "$work/witness"
exit 0
FAKE
chmod +x "$work/fakebin/uv"

# A PATH without uv: only the tools the hooks themselves need.
mkdir -p "$work/nouv"
for tool in bash git python3 cat head tail realpath dirname; do
    ln -s "$(command -v "$tool")" "$work/nouv/$tool"
done

failures=0
out="" err="" code=0

reset_tree() {
    (cd "$proj" && git checkout -q -- . && git clean -fdq -e .venv -e uv.lock)
    rm -f "$work/witness"
}

# run_hook <script> <stdin-json> [PATH prefix] [full PATH replacing the current one]
run_hook() {
    local script="$1" input="$2" prefix="${3:-}" full="${4:-$PATH}"
    local errfile="$work/stderr"
    out="$(cd "$work" && printf '%s' "$input" \
        | PATH="${prefix:+$prefix:}$full" CLAUDE_PROJECT_DIR="$proj" "$BASH" "$hooks/$script" 2>"$errfile")"
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

edit_json() { printf '{"tool_input":{"file_path":"%s"}}' "$1"; }

case_non_python_ignored() {
    reset_tree
    run_hook py-check.sh '{"tool_input":{"file_path":"README.md"}}'
    [ "$code" = 0 ] && [ -z "$err" ] && [ -z "$out" ]
}

case_python_ok() {
    reset_tree
    run_hook py-check.sh "$(edit_json "$proj/src/fixture/__init__.py")"
    [ "$code" = 0 ]
}

case_python_is_formatted() {
    reset_tree
    printf '"""Fixture."""\n\nx=1\n' > "$proj/src/fixture/__init__.py"
    run_hook py-check.sh "$(edit_json "$proj/src/fixture/__init__.py")"
    [ "$code" = 0 ] && grep -qx 'x = 1' "$proj/src/fixture/__init__.py"
}

case_python_type_error_blocks() {
    reset_tree
    printf 'def f() -> int:\n    return "a"\n' > "$proj/src/fixture/__init__.py"
    run_hook py-check.sh "$(edit_json "$proj/src/fixture/__init__.py")"
    [ "$code" = 2 ] && [[ "$err" == *"vérification Python en échec"* ]] \
        && [[ "$err" == *"is not assignable"* ]]
}

case_odd_file_name_is_safe() {
    reset_tree
    local odd="$proj/src/fixture/a b \$x.py"
    printf 'def f() -> int:\n    return "a"\n' > "$odd"
    run_hook py-check.sh "$(edit_json "$odd")"
    [ "$code" = 2 ] && [ ! -e "$proj/\$x" ] && [ ! -e "$proj/src/fixture/\$x" ] \
        && [ ! -e "$work/\$x" ]
}

case_outside_project_ignored() {
    reset_tree
    printf 'def f( -> :\n' > "$work/outside.py"
    run_hook py-check.sh "$(edit_json "$work/outside.py")"
    [ "$code" = 0 ] || return 1
    [ -z "$err" ] || return 1
    run_hook py-check.sh "$(edit_json "$proj/src/fixture/missing.py")"
    [ "$code" = 0 ] && [ -z "$err" ]
}

case_missing_uv_does_not_block_edit() {
    reset_tree
    run_hook py-check.sh "$(edit_json "$proj/src/fixture/__init__.py")" "" "$work/nouv"
    [ "$code" = 0 ] && [[ "$err" == *"uv introuvable"* ]]
}

case_missing_uv_blocks_stop() {
    reset_tree
    printf 'x = 1\n' > "$proj/src/fixture/extra.py"
    run_hook verify.sh '{"stop_hook_active":false}' "" "$work/nouv"
    [ "$code" = 2 ] && [[ "$err" == *"uv introuvable"* ]]
}

case_verify_clean_tree() {
    reset_tree
    run_hook verify.sh '{"stop_hook_active":false}' "$work/fakebin"
    [ "$code" = 0 ] && [ ! -e "$work/witness" ]
}

add_failing_test() {
    printf 'def test_fail():\n    assert 1 == 2\n' > "$proj/tests/test_fail.py"
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

for c in non_python_ignored python_ok python_is_formatted python_type_error_blocks \
    odd_file_name_is_safe outside_project_ignored missing_uv_does_not_block_edit \
    missing_uv_blocks_stop verify_clean_tree verify_failing_blocks verify_loop_guard; do
    if "case_$c"; then report "$c" 1; else report "$c" 0; fi
done

exit $((failures > 0 ? 1 : 0))
