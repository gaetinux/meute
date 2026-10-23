"""Git failures as meute errors: git missing from the `PATH`, or a git command that failed."""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

from meute.core.errors import MeuteError
from meute.git.run import GitError, find_git

GIT_NOT_FOUND = "git not found"


@contextmanager
def git_errors() -> Generator[None]:
    """Turn a `GitError` into a `MeuteError` with the same text."""
    try:
        yield
    except GitError as failure:
        raise MeuteError(str(failure)) from failure


def find_git_or_fail(environ: Mapping[str, str]) -> Path:
    """The git binary of `environ`.

    Raises:
        MeuteError: there is none.
    """
    git = find_git(environ)
    if git is None:
        raise MeuteError(GIT_NOT_FOUND)
    return git
