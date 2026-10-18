"""Interpretation of Claude Code hooks into session states (spec 7.1, corrected by spike S7)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import TypeGuard

from meute.core.session_state import (
    Compacting,
    Exited,
    Idle,
    PermissionRequested,
    Running,
    SessionState,
    SubagentRunning,
    WaitingInput,
)
from meute.core.text import one_line, printable

type _Handler = Callable[[Mapping[str, object]], HookEffect | None]

_ID_MAX = 300
_EXCERPT_MAX = 80
_MESSAGE_MAX = 500
_NOTE_MAX = 200
_PATH_KEYS = {
    "Bash": "command",
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
    "NotebookEdit": "file_path",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class HookEffect:
    """What a hook changes; None means "unchanged". `history` goes to `session_events.detail`."""

    state: SessionState | None
    native_id: str | None = None
    transcript_path: str | None = None
    model: str | None = None
    permission_mode: str | None = None
    last_tool: str | None = None
    pending_permission: str | None = None
    last_message: str | None = None
    history: str


def _is_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _fields(value: object) -> dict[str, object]:
    """Return the string-keyed entries of `value`, empty when it is not a JSON object."""
    if not _is_dict(value):
        return {}
    return {key: item for key, item in value.items() if isinstance(key, str)}


def _text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _capped(payload: Mapping[str, object], key: str, limit: int) -> str | None:
    value = _text(payload, key)
    return None if value is None else one_line(value, limit, ellipsis=True)


def tool_excerpt(tool_name: str, tool_input: object) -> str:
    """Return `"<tool_name> <excerpt>"` of a tool call, or `"<tool_name>"` without excerpt.

    The excerpt is the command (`Bash`), the file path (`Read`, `Edit`, `Write`,
    `NotebookEdit`) or the first string value; one line, 80 characters at most.
    """
    fields = _fields(tool_input)
    chosen = fields.get(_PATH_KEYS.get(tool_name, ""))
    if not isinstance(chosen, str):
        chosen = next((item for item in fields.values() if isinstance(item, str)), "")
    excerpt = one_line(chosen, _EXCERPT_MAX, ellipsis=True)
    return f"{tool_name} {excerpt}" if excerpt else tool_name


def _tool(payload: Mapping[str, object]) -> str:
    return tool_excerpt(_text(payload, "tool_name") or "", payload.get("tool_input"))


def _model(payload: Mapping[str, object]) -> str | None:
    model = payload.get("model")
    identifier = model if isinstance(model, str) else _fields(model).get("id")
    return one_line(identifier, _NOTE_MAX, ellipsis=True) if isinstance(identifier, str) else None


def _mode(payload: Mapping[str, object]) -> str | None:
    mode = _capped(payload, "permission_mode", _NOTE_MAX)
    return "manual" if mode == "default" else mode  # S7: Claude reports manual as default


def _start(payload: Mapping[str, object]) -> HookEffect:
    return HookEffect(
        state=Idle(),
        transcript_path=_capped(payload, "transcript_path", _ID_MAX),
        model=_model(payload),
        history=one_line(_text(payload, "source") or "", _NOTE_MAX, ellipsis=True),
    )


def _stop(payload: Mapping[str, object]) -> HookEffect:
    message = _text(payload, "last_assistant_message")
    return HookEffect(
        state=WaitingInput(),
        last_message=None
        if message is None
        else printable(message, keep_newlines=True)[:_MESSAGE_MAX],
        history="",
    )


def _subagent(event: str, payload: Mapping[str, object]) -> HookEffect | None:
    agent_type = _text(payload, "agent_type")
    if not agent_type:  # /compact sends SubagentStop with an empty type, without a start
        return None
    state = SubagentRunning() if event == "SubagentStart" else Running()
    return HookEffect(state=state, history=one_line(agent_type, _NOTE_MAX, ellipsis=True))


def _simple(state: SessionState) -> _Handler:
    return lambda _payload: HookEffect(state=state, history="")


def _pre_tool(payload: Mapping[str, object]) -> HookEffect:
    tool = _tool(payload)
    return HookEffect(state=Running(), last_tool=tool, history=tool)


def _permission(payload: Mapping[str, object]) -> HookEffect:
    tool = _tool(payload)
    return HookEffect(state=PermissionRequested(), pending_permission=tool, history=tool)


def _prompt(payload: Mapping[str, object]) -> HookEffect:
    return HookEffect(state=Running(), permission_mode=_mode(payload), history="")


def _noted(state: SessionState | None, key: str) -> _Handler:
    return lambda payload: HookEffect(
        state=state, history=one_line(_text(payload, key) or "", _NOTE_MAX, ellipsis=True)
    )


_HANDLERS: dict[str, _Handler] = {
    "SessionStart": _start,
    "UserPromptSubmit": _prompt,
    "PreToolUse": _pre_tool,
    "PermissionRequest": _permission,
    "PostToolUse": _simple(Running()),
    "PreCompact": _simple(Compacting()),
    "SubagentStart": lambda payload: _subagent("SubagentStart", payload),
    "SubagentStop": lambda payload: _subagent("SubagentStop", payload),
    "Stop": _stop,
    "SessionEnd": _noted(Exited(code=None), "reason"),
    "Notification": _noted(None, "message"),
}


def interpret_hook(event: str, payload: Mapping[str, object]) -> HookEffect | None:
    """Interpret one hook; None means the hook is ignored. Never raises."""
    handler = _HANDLERS.get(event)
    effect = (
        HookEffect(state=None, history=one_line(event, _NOTE_MAX, ellipsis=True))
        if handler is None
        else handler(payload)
    )
    if effect is None:
        return None
    return replace(effect, native_id=_capped(payload, "session_id", _ID_MAX) or None)
