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

Dashboard, Tasks tab (`Tab` or a click on the title switches tabs; `?` lists every key):

| Key | Action |
|---|---|
| `a` | add a task (quick entry: `title @project !! >tomorrow`) |
| `f` / `g` | cycle the filter (all, this project, floating) / the grouping (urgency, project) |
| `s` / `p` | status / priority of the selected task |
| `d` | postpone (+1h, tonight 6pm, tomorrow 9am, Monday 9am, clear) |
| `e` / `D` / `@` | edit the title / the description / the project |
| `o` | add a note |
| `L` | launch Claude on the task; its text is pasted, not sent |
| `Del` | delete (asks for confirmation) |

## Development

```bash
uv sync
bash scripts/verify.sh
```

`scripts/verify.sh` is the full check run by CI. The development guide, [docs/dev/developpement-assiste-par-ia.md](docs/dev/developpement-assiste-par-ia.md), is written in French.

## License

MIT OR Apache-2.0, at your option. See [LICENSE-MIT](LICENSE-MIT) and [LICENSE-APACHE](LICENSE-APACHE).
