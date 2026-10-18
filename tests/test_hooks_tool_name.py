"""The tool name of a hook is Claude's data: one printable line, capped like the excerpt."""

from meute.core.hooks import interpret_hook, tool_excerpt

RLO = chr(0x202E)  # right-to-left override


def test_tool_name_is_one_printable_capped_line() -> None:
    name = ("\x1b[31mBa\nsh" + RLO) * 100
    shown = tool_excerpt(name, {"command": "ls"})
    assert "\x1b" not in shown
    assert "\n" not in shown
    assert RLO not in shown
    assert len(shown) <= 200 + 1 + 80


def test_hook_tool_name_is_sanitised() -> None:
    effect = interpret_hook("PreToolUse", {"tool_name": "Bash\x1b]0;x\x07", "tool_input": {}})
    assert effect is not None
    assert effect.last_tool is not None
    assert "\x1b" not in effect.last_tool
    assert "\x07" not in effect.last_tool
