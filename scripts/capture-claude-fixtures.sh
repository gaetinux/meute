#!/usr/bin/env bash
# Spike S7: capture real Claude Code hook, statusline and `claude agents --json` messages,
# then write sanitised copies as test fixtures.
#
# Usage: bash scripts/capture-claude-fixtures.sh [raw-capture-dir]
#
# Costs real Claude usage (about $0.50 with claude-opus-5-5 on 2026-10-18). Safety rules:
# - Claude runs in this repository (already trusted: no trust question, nothing new in ~/.claude.json),
#   with `--settings <capture file>` and `--permission-mode manual`; nothing under ~/.claude is edited.
# - Everything runs on a throw-away tmux server `-L meute-capture-<uuid> -f /dev/null`, killed on exit.
# - The only permission approved is a Bash call whose command is exactly `echo meute-capture`;
#   any other permission request is denied (Escape). One `mkdir <raw-capture-dir>/denied` is asked
#   for on purpose, to capture a PermissionRequest, and denied.
# Raw captures stay in the raw-capture dir (default: a new mktemp dir); only sanitised copies are
# written to tests/fixtures/claude/<version>/.
set -euo pipefail

repo="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
version="$(claude --version | cut -d' ' -f1)"
[ -n "$version" ] || { echo "cannot read claude version" >&2; exit 1; }
out="$(realpath "${1:-$(mktemp -d)}")"
fixtures="$repo/tests/fixtures/claude/$version"
raw="$out/raw"
mkdir -p "$raw"
rm -f "$raw"/*

main_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
dash_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
sock="meute-capture-$(python3 -c 'import uuid; print(uuid.uuid4())')"
tm() { tmux -L "$sock" -f /dev/null "$@"; }
# kill-server can leave the socket file behind: remove exactly that path, never a glob.
stop_server() { tm kill-server 2>/dev/null || true; rm -f "${TMUX_TMPDIR:-/tmp}/tmux-$(id -u)/$sock"; }
trap stop_server EXIT INT TERM

# Every hook and the statusline copy stdin to raw/<MEUTE_SESSION>-<kind>-<nanoseconds>.json.
cat >"$out/capture.sh" <<'EOF'
#!/usr/bin/env bash
cat >"$(dirname "$0")/raw/${MEUTE_SESSION:-none}-$1-$(date +%s%N).json"
if [ "$1" = statusline ]; then printf 'meute-capture'; fi
EOF
chmod +x "$out/capture.sh"
events=(SessionStart UserPromptSubmit PreToolUse PermissionRequest PostToolUse PreCompact
    SubagentStart SubagentStop Stop SessionEnd Notification)
python3 - "$out" "${events[@]}" >"$out/settings.json" <<'EOF'
import json, shlex, sys
script = shlex.quote(sys.argv[1] + "/capture.sh")
hooks = {e: [{"hooks": [{"type": "command", "command": f"{script} {e}"}]}] for e in sys.argv[2:]}
status = {"type": "command", "command": f"{script} statusline"}
print(json.dumps({"hooks": hooks, "statusLine": status}, indent=2))
EOF

count() { find "$raw" -name "$1-$2-*.json" | wc -l; }
latest() { find "$raw" -name "$1-$2-*.json" | sort | tail -n 1; }
pane() { tm capture-pane -p -t "capture:$1"; }
send() { tm send-keys -t "capture:$1" -l "$2"; sleep 0.3; tm send-keys -t "capture:$1" Enter; }
handled=0
# Answers the newest permission request of window $1: "Yes" only for exactly `echo meute-capture`.
answer() {
    local deadline=$((SECONDS + 30))
    until pane "$1" | grep -q 'Do you want'; do [ "$SECONDS" -lt "$deadline" ] || break; sleep 0.2; done
    if python3 - "$(latest "$1" PermissionRequest)" <<'EOF'
import json, sys
msg = json.load(open(sys.argv[1]))
command = msg.get("tool_input", {}).get("command", "")
sys.exit(0 if msg.get("tool_name") == "Bash" and command.strip() == "echo meute-capture" else 1)
EOF
    then
        echo "permission request: approving echo meute-capture" >&2
        tm send-keys -t "capture:$1" Enter # "1. Yes" is the default choice
    else
        echo "permission request: denying" >&2
        tm send-keys -t "capture:$1" Escape
    fi
    handled=$((handled + 1))
}
# Waits until window $1 has at least $3 messages of kind $2, answering permission requests meanwhile.
wait_for() {
    local deadline=$((SECONDS + ${4:-180}))
    until [ "$(count "$1" "$2")" -ge "$3" ]; do
        if [ "$2" != PermissionRequest ] && [ "$(count "$1" PermissionRequest)" -gt "$handled" ]; then
            answer "$1"
        fi
        [ "$SECONDS" -lt "$deadline" ] || { echo "timeout waiting for $1 $2 >= $3" >&2; pane "$1" >&2; return 1; }
        sleep 0.2
    done
}
turn() { # turn <window> <prompt>: sends the prompt, waits for its Stop
    local stops
    stops="$(count "$1" Stop)"
    send "$1" "$2"
    wait_for "$1" Stop $((stops + 1))
}
start() { # start <window> <session-id> <name>
    tm new-window -d -n "$1" -c "$repo" -e "MEUTE_SESSION=$1" -- \
        claude --settings "$out/settings.json" --session-id "$2" --permission-mode manual "--name=$3"
    wait_for "$1" SessionStart 1 60
    wait_for "$1" statusline 1 60
}

tm new-session -d -s capture -x 200 -y 50 -c "$repo"
start main "$main_id" meute-capture

turn main 'Reply with the single word pong.'

# Claude Code 2.1.302 runs `echo` without asking; the approval path stays for versions that ask.
turn main 'Run the shell command: echo meute-capture'

# A command that does ask, to capture PermissionRequest; it is denied, so nothing is created.
send main "Run the shell command: mkdir $out/denied"
wait_for main PermissionRequest $((handled + 1))
answer main
deadline=$((SECONDS + 30))
until pane main | grep -q 'Interrupted'; do [ "$SECONDS" -lt "$deadline" ] || break; sleep 0.2; done
sleep 1 # lets a Stop for the denied turn, if any, land before the next turn counts

turn main 'Use the Task tool with a general-purpose subagent to reply pong.'

send main '/compact'
wait_for main PreCompact 1
wait_for main SessionStart 2 120 || true # source "compact", if any
deadline=$((SECONDS + 120))
until pane main | grep -q 'Compacted'; do [ "$SECONDS" -lt "$deadline" ] || break; sleep 0.2; done

# A second session, whose title starts with "-", runs alongside while `claude agents --json` is timed.
start dash "$dash_id" -meute-capture-dash
claude agents --json >"$raw/agents.json"
hyperfine -N --runs 10 --export-json "$raw/hyperfine.json" 'claude agents --json' >"$raw/hyperfine.txt"
pane main >"$raw/pane-main.txt"
pane dash >"$raw/pane-dash.txt"

for w in dash main; do
    send "$w" '/exit'
    wait_for "$w" SessionEnd 1 60
done
stop_server
trap - EXIT INT TERM

# Sanitise into the fixtures.
rm -rf "$fixtures"
mkdir -p "$fixtures/hooks"
python3 - "$raw" "$fixtures" "$out" "$HOME" "$(id -un)" "$main_id" "$dash_id" <<'EOF'
import json, re, sys
from pathlib import Path

raw, fixtures, out, home, user, main_id, dash_id = sys.argv[1:]
raw, fixtures = Path(raw), Path(fixtures)
projects = re.compile(re.escape(home) + r"/\.claude/projects/[^/\"]+/")
email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def clean(text: str) -> str:
    text = projects.sub("/home/user/.claude/projects/x/", text)
    text = text.replace(out, "/tmp/capture").replace(home, "/home/user")
    text = re.sub(rf"\b{re.escape(user)}\b", "user", text)
    return email.sub("redacted", text)


def write(path: Path, data: object) -> None:
    path.write_text(clean(json.dumps(data, indent=2, ensure_ascii=False)) + "\n")


counters: dict[str, int] = {}
statuslines = []
for file in sorted(raw.glob("*-*-*.json"), key=lambda p: int(p.stem.rsplit("-", 1)[1])):
    _, kind, _ = file.stem.split("-")
    data = json.loads(file.read_text())
    if kind == "statusline":
        statuslines.append(data)
        continue
    counters[kind] = counters.get(kind, 0) + 1
    write(fixtures / "hooks" / f"{kind}-{counters[kind]}.json", data)

# Statusline: keep each distinct shape (set of key paths) once, in order of arrival.
def shape(value: object, prefix: str = "") -> frozenset[str]:
    if isinstance(value, dict):
        return frozenset({prefix}).union(*(shape(v, f"{prefix}.{k}") for k, v in value.items()))
    return frozenset({prefix})

seen: set[frozenset[str]] = set()
for data in statuslines:
    if (s := shape(data)) not in seen:
        seen.add(s)
        write(fixtures / f"statusline-{len(seen)}.json", data)

agents = json.loads((raw / "agents.json").read_text())
ours = [a for a in agents if a.get("sessionId") in (main_id, dash_id)]
write(fixtures / "agents.json", ours)
write(fixtures / "settings.json", json.loads((Path(out) / "settings.json").read_text()))
print(f"{sum(counters.values())} hooks, {len(seen)} statuslines, {len(ours)}/{len(agents)} agents kept")
EOF
echo "raw captures: $raw"
echo "fixtures: $fixtures"
