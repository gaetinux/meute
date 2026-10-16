import pytest

from meute import cli


def _raising(code: object):  # noqa: ANN202 — tiny test double
    def fake_app(*, args: list[str], prog_name: str) -> None:  # noqa: ARG001 — mimics Typer
        raise SystemExit(code)

    return fake_app


def test_run_maps_system_exit_none_to_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "app", _raising(None))
    assert cli.run([]) == 0


def test_run_keeps_an_integer_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "app", _raising(3))
    assert cli.run([]) == 3


def test_run_prints_a_string_exit_message_to_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "app", _raising("boom"))
    assert cli.run([]) == 1
    captured = capsys.readouterr()
    assert captured.err == "boom\n"
    assert captured.out == ""
