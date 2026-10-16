"""Hook and statusline ingestion: the latency-critical path, stdlib only."""

import sys
from collections.abc import Sequence


def run(args: Sequence[str]) -> int:  # noqa: ARG001 — arguments are ignored for now
    """Consume stdin and succeed; ingestion must never disturb Claude Code."""
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001 — spec § 7.3: ingest never fails
        return 0
    return 0
