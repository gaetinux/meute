# meute

meute is a CLI/TUI that drives several Claude Code sessions and Bash terminals in parallel from one terminal, including over SSH, and links them to lightweight task management.

**Status:** Pre-alpha, being rewritten in Python.

## Installation

From source, with [uv](https://docs.astral.sh/uv/) and Python 3.13:

```bash
uv tool install --compile-bytecode .
```

`--compile-bytecode` is optional. The startup spike measured no gain on warm runs (about 47 ms either way for the 50 ms budget of `meute ingest`); it only moves bytecode compilation to install time.

## Development

```bash
uv sync
bash scripts/verify.sh
```

`scripts/verify.sh` is the full check run by CI. The development guide, [docs/dev/developpement-assiste-par-ia.md](docs/dev/developpement-assiste-par-ia.md), is written in French.

## License

MIT OR Apache-2.0, at your option. See [LICENSE-MIT](LICENSE-MIT) and [LICENSE-APACHE](LICENSE-APACHE).
