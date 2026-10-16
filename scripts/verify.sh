#!/usr/bin/env bash
set -euo pipefail

uv lock --check
uv run --frozen ruff format --check
uv run --frozen ruff check
uv run --frozen basedpyright
uv run --frozen lint-imports
uv run --frozen pytest
uv run --frozen deptry src
req="$(mktemp)"; trap 'rm -f "$req"' EXIT
uv export --frozen --no-emit-project --format requirements-txt -o "$req" >/dev/null
uv run --frozen pip-audit --strict --disable-pip --require-hashes -r "$req"
# "Mozilla Public License 2.0" is how certifi (a pip-audit dependency) spells MPL-2.0.
uv run --frozen --with pip-licenses pip-licenses --partial-match \
  --allow-only "MIT;BSD;Apache;ISC;Python Software Foundation;PSF;MPL-2.0;Mozilla Public License 2.0"
