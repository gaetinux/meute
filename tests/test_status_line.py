import pytest

from meute.core.status_line import status_text


@pytest.mark.parametrize(
    ("displayed", "attention", "five_hour", "expected"),
    [
        (None, 0, None, ""),
        ("api", 0, None, "▶ api"),
        ("api", 2, None, "▶ api · 2 need attention"),
        ("api", 0, 42.4, "▶ api · 5h 42%"),
        ("api", 1, 99.6, "▶ api · 1 need attention · 5h 100%"),
        (None, 3, 10.0, "3 need attention · 5h 10%"),
        (None, 0, 0.0, "5h 0%"),
        ("a\x1b[31mb", 0, None, "▶ a�[31mb"),
    ],
)
def test_status_text(
    displayed: str | None, attention: int, five_hour: float | None, expected: str
) -> None:
    assert status_text(displayed, attention, five_hour) == expected
