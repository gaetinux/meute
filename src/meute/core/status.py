"""Task status, priority and their parsing."""

from dataclasses import dataclass
from enum import Enum

from meute.core.errors import InvalidInput


class StatusKind(Enum):
    """The kind of a task status, without the data some kinds carry."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"

    @property
    def label(self) -> str:
        """Human-readable label."""
        match self:
            case StatusKind.TODO:
                return "to do"
            case StatusKind.IN_PROGRESS:
                return "in progress"
            case StatusKind.BLOCKED:
                return "blocked"
            case StatusKind.REVIEW:
                return "in review"
            case StatusKind.DONE:
                return "done"

    @property
    def symbol(self) -> str:
        """One-character symbol (specification section 9.5)."""
        match self:
            case StatusKind.TODO:
                return "·"
            case StatusKind.IN_PROGRESS:
                return "»"
            case StatusKind.BLOCKED:
                return "✕"
            case StatusKind.REVIEW:
                return "◎"
            case StatusKind.DONE:
                return "✓"


def parse_status_kind(text: str) -> StatusKind:
    """Return the kind whose value is `text`.

    Raises:
        InvalidInput: no kind has this value.
    """
    try:
        return StatusKind(text)
    except ValueError:
        message = f"unknown status: {text}"
        raise InvalidInput(message) from None


@dataclass(frozen=True, slots=True, kw_only=True)
class Todo:
    """Not started."""


@dataclass(frozen=True, slots=True, kw_only=True)
class InProgress:
    """Being worked on."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Blocked:
    """Cannot move on; the reason is mandatory, non-empty and trimmed."""

    reason: str

    def __post_init__(self) -> None:
        """Reject an empty or untrimmed reason."""
        if not self.reason or self.reason != self.reason.strip():
            message = "a blocked task needs a non-empty reason"
            raise InvalidInput(message)


@dataclass(frozen=True, slots=True, kw_only=True)
class Review:
    """Waiting for a review."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Done:
    """Finished."""


TaskStatus = Todo | InProgress | Blocked | Review | Done


def status_kind(status: TaskStatus) -> StatusKind:
    """Return the kind of `status`."""
    match status:
        case Todo():
            return StatusKind.TODO
        case InProgress():
            return StatusKind.IN_PROGRESS
        case Blocked():
            return StatusKind.BLOCKED
        case Review():
            return StatusKind.REVIEW
        case Done():
            return StatusKind.DONE


def status_text(status: TaskStatus) -> str:
    """Return the kind value, or `blocked: <reason>` for a blocked status."""
    if isinstance(status, Blocked):
        return f"blocked: {status.reason}"
    return status_kind(status).value


def is_open(status: TaskStatus) -> bool:
    """Return whether the task is still open, that is not done."""
    return not isinstance(status, Done)


def status_from_kind(kind: StatusKind, reason: str | None = None) -> TaskStatus:
    """Build the status of `kind`; `reason` is trimmed and used only for `BLOCKED`.

    Raises:
        InvalidInput: `kind` is `BLOCKED` and `reason` is missing or blank.
    """
    match kind:
        case StatusKind.TODO:
            return Todo()
        case StatusKind.IN_PROGRESS:
            return InProgress()
        case StatusKind.BLOCKED:
            return Blocked(reason=(reason or "").strip())
        case StatusKind.REVIEW:
            return Review()
        case StatusKind.DONE:
            return Done()


class Priority(Enum):
    """Task priority, most urgent first."""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

    @property
    def marker(self) -> str:
        """Marker shown in lists: `!!`, `!` or nothing."""
        match self:
            case Priority.URGENT:
                return "!!"
            case Priority.HIGH:
                return "!"
            case Priority.NORMAL | Priority.LOW:
                return ""

    @property
    def rank(self) -> int:
        """Sort key from 0 (urgent) to 3 (low)."""
        match self:
            case Priority.URGENT:
                return 0
            case Priority.HIGH:
                return 1
            case Priority.NORMAL:
                return 2
            case Priority.LOW:
                return 3


def parse_priority(text: str) -> Priority:
    """Return the priority whose value is `text`.

    Raises:
        InvalidInput: no priority has this value.
    """
    try:
        return Priority(text)
    except ValueError:
        message = f"unknown priority: {text}"
        raise InvalidInput(message) from None
