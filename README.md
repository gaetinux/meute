# meute

meute is a CLI/TUI that drives several Claude Code sessions and Bash terminals in parallel from one terminal, including over SSH, and links them to lightweight task management.

**Status:** Pre-alpha, being rewritten in Python.

## Installation

From source, with [uv](https://docs.astral.sh/uv/) and Python 3.13:

```bash
uv tool install --compile-bytecode .
```

`--compile-bytecode` is optional. The startup spike measured no gain on warm runs (about 47 ms either way for the 50 ms budget of `meute ingest`); it only moves bytecode compilation to install time.

## Keys

Global keys (they work from any pane; rebind them in `config.toml` under `[keys]`). The bar at the bottom of the screen always lists them, as configured; where the dashboard is hidden it adds the meute status (displayed session, attention, 5 h quota, overdue tasks):

| Key | Action |
|---|---|
| `M-p` / `M-o` | focus the dashboard / the main area |
| `M-n` / `M-N` | next / previous session that needs attention |
| `M-t` | quick task window: type a task, `Enter` creates it, `Esc` cancels (needs tmux 3.3 or later) |
| `M-q` | detach, everything keeps running |

Dashboard, Sessions tab (`?` lists every key):

| Key | Action |
|---|---|
| `Enter` | show the selected session in the main area (on a repository: start a Bash session there) |
| `c` | new Claude session on the selected repository or session |
| `n` | new session of the type last used in that repository (Claude when it has none) |
| `N` | open the launch form: type, repository, folder, title, and for Claude the task and the permission mode; `Tab` next field, `←` `→` choose, `Enter` launch, `Esc` cancel; with a task, `Work on task #N.` is pasted into Claude unsent, like `L` |
| `W` | remove the Git worktree of an ended session (`git worktree remove`, the branch is kept); asks for confirmation, and when it still has uncommitted changes or unpushed commits, `y` lists them before a second `remove anyway? y/n` |
| `r` | resume an ended Claude session (`claude --resume`, in its old pane when it is still there) |
| `x` | stop the session (asks for confirmation); when it was the one shown, the next live session of the board takes its place |
| `a` / `e` | show only what needs attention / show ended sessions |

Each session card's third line shows the Git state of its folder, polled in the background every 10 s at most: `└ main* +12 −3 ↑2 ↓1` (`*` uncommitted changes, untracked files included; added and removed lines; commits ahead of and behind the upstream), `└ feat/x (not pushed)` for a branch without upstream, `└ (detached a1b2c3d)`. Bash sessions get it too. meute never commits, merges, pushes or fetches.

In the launch form, a `Worktree` field follows `Repo`: `none` (the folder as typed), `new` (a `Branch` field, prefilled from the title, and the computed path `→ ~/git/<repo>.worktrees/<branch>`; launching runs `git worktree add <path> -b <branch>` from the repository's HEAD), or an existing linked worktree (`<branch>  <path>`). When another live session already works in the repository's folder, the form opens on `new` and warns `⚠ another live session works in this folder: a new worktree is recommended`; `←` goes back to `none`.

On an orphan pane (a pane tagged for meute that the database does not know), `Enter` shows it, `a` adopts it as a session and `x` closes it (asks for confirmation; a shown orphan is replaced by the first live session of the board).

Dashboard, Tasks tab (`Tab` or a click on the title switches tabs; `?` lists every key):

| Key | Action |
|---|---|
| `a` | add a task (quick entry: `title @project !! >tomorrow`) |
| `f` / `g` | cycle the filter (all, this project, floating) / the grouping (urgency, project) |
| `s` / `p` | status / priority of the selected task |
| `d` | postpone (+1h, tonight 6pm, tomorrow 9am, Monday 9am, clear) |
| `e` / `D` / `@` | edit the title / the description / the project |
| `o` | add a note |
| `L` | launch Claude on the task; `Work on task #N.` is pasted, not sent, and Claude reads the task with the `task_read` tool |
| `Del` | delete (asks for confirmation) |

## Worktrees

```bash
meute session new --worktree feat/x        # new worktree of the repository of --cwd (or here), session started in it
meute worktree list [<repo>] [--json]      # linked worktrees of the known repositories: path, branch, * when changed, locked, missing
meute worktree remove <path> [--yes] [--force]
```

`meute worktree remove` never touches a repository's main folder, a locked worktree or one where a live session works, and always keeps the branch. Without `--force` it refuses a worktree with uncommitted changes or commits found on no remote and no other local branch, and lists them; `--force` removes it anyway after a confirmation (`--yes` skips it).

## Claude and tasks (MCP)

Every Claude session meute starts gets a `meute` MCP server (`meute mcp`, stdio) through `--mcp-config`, so Claude reads and updates its own tasks. The seven tools (`task_list`, `task_read`, `task_create`, `task_update`, `task_set_status`, `task_note_add`, `task_link_session`) are allowed without a prompt; none deletes anything. Writes are recorded as `claude/mcp` with the calling session.

Instructions are composed into the session's system prompt: global ones, the project's, and a line naming the linked task. They are empty by default.

```bash
meute config set claude.instructions "Answer tersely."      # global, [claude] instructions
meute project edit myproject --instructions "Tests first."  # or --instructions-file notes.md; "" clears
meute project show myproject                                # description, instructions, repositories
```

A context up to 8 000 bytes goes in the command line; a longer one goes through a private file in the session's folder.

## Development

```bash
uv sync
bash scripts/verify.sh
```

`scripts/verify.sh` is the full check run by CI. The development guide, [docs/dev/developpement-assiste-par-ia.md](docs/dev/developpement-assiste-par-ia.md), is written in French.

## License

MIT OR Apache-2.0, at your option. See [LICENSE-MIT](LICENSE-MIT) and [LICENSE-APACHE](LICENSE-APACHE).
