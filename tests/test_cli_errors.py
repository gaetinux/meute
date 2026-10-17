"""Error reporting of the command line."""

from conftest import Sandbox


def test_os_error_is_printed_exactly_once(sandbox: Sandbox) -> None:
    blocker = sandbox.root / "not-a-dir"
    blocker.write_text("", encoding="utf-8")
    result = sandbox.run("task", "list", env={"XDG_DATA_HOME": str(blocker)})
    assert result.returncode == 1
    assert result.stderr.startswith("meute: ")
    assert result.stderr.count("Not a directory") == 1
    assert "Traceback" not in result.stderr
