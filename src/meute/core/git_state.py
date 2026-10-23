"""The Git state of a folder: parsers of `git status` and `git diff --numstat`, and its text."""

from dataclasses import dataclass

from meute.core.text import printable

_SHORT_OID = 7
_MAX_DIGITS = 18
_MINUS = chr(0x2212)
_LINE_BREAKS = {
    0x2028: 0xFFFD,
    0x2029: 0xFFFD,
}  # `printable` keeps them, `splitlines` breaks on them


@dataclass(frozen=True, slots=True, kw_only=True)
class GitState:
    """Where a folder stands in Git.

    Attributes:
        branch: The branch name, or None when HEAD is detached.
        detached: The short commit of a detached HEAD, else None.
        upstream: Whether the branch tracks an upstream.
        ahead: Commits not yet in the upstream.
        behind: Upstream commits not yet here.
        dirty: Whether the working tree has changes, untracked files included.
        added: Lines added since HEAD, staged or not.
        removed: Lines removed since HEAD, staged or not.
    """

    branch: str | None
    detached: str | None
    upstream: bool
    ahead: int
    behind: int
    dirty: bool
    added: int = 0
    removed: int = 0


def parse_status_v2(text: str) -> GitState | None:
    """Read the output of `git status --porcelain=v2 --branch`.

    Any entry line (`1`, `2`, `u`, `?`) means the tree is dirty. Returns None without a
    `# branch.head` line. Never raises.
    """
    head: str | None = None
    oid = ""
    upstream = False
    ahead = behind = 0
    dirty = False
    for line in text.splitlines():
        if line.startswith("# branch.head "):
            head = line.removeprefix("# branch.head ")
        elif line.startswith("# branch.oid "):
            oid = line.removeprefix("# branch.oid ")
        elif line.startswith("# branch.upstream "):
            upstream = True
        elif line.startswith("# branch.ab "):
            ahead, behind = _ahead_behind(line.removeprefix("# branch.ab "))
        elif line.strip() and not line.startswith("#"):
            dirty = True
    if head is None:
        return None
    detached = (oid[:_SHORT_OID] or "?") if head == "(detached)" else None
    return GitState(
        branch=None if detached is not None else head,
        detached=detached,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        dirty=dirty,
    )


def _ahead_behind(text: str) -> tuple[int, int]:
    words = text.split()
    if len(words) != 2 or words[0][:1] != "+" or words[1][:1] != "-":  # noqa: PLR2004 — "+A -B"
        return 0, 0
    ahead, behind = _count(words[0][1:]), _count(words[1][1:])
    return (ahead, behind) if ahead is not None and behind is not None else (0, 0)


def _count(word: str) -> int | None:
    return int(word) if word.isascii() and word.isdigit() and len(word) <= _MAX_DIGITS else None


def parse_numstat(text: str) -> tuple[int, int]:
    """Sum the added and removed lines of `git diff --numstat`.

    A binary file (`-`) counts as 0 and a malformed line is skipped. Never raises.
    """
    added = removed = 0
    for line in text.splitlines():
        columns = line.split("\t", 2)
        if len(columns) != 3:  # noqa: PLR2004 — added, removed, path
            continue
        plus, minus = _numstat_count(columns[0]), _numstat_count(columns[1])
        if plus is not None and minus is not None:
            added += plus
            removed += minus
    return added, removed


def _numstat_count(word: str) -> int | None:
    return 0 if word == "-" else _count(word)


def git_text(state: GitState) -> str:
    """The card text of a Git state: branch, `*` if dirty, line counts, ahead and behind."""
    if state.detached is not None:
        name = f"(detached {state.detached})"
    else:
        name = state.branch if state.branch is not None else "HEAD"
    parts = [name + ("*" if state.dirty else "")]
    if state.added or state.removed:
        parts.append(f"+{state.added} {_MINUS}{state.removed}")
    if state.ahead:
        parts.append(f"↑{state.ahead}")
    if state.behind:
        parts.append(f"↓{state.behind}")
    if not state.upstream and state.detached is None:
        parts.append("(not pushed)")
    return printable(" ".join(parts)).translate(_LINE_BREAKS)
