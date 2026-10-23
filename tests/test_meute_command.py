"""`meute_command()` ignores the current folder: a repository cannot shadow meute's imports."""

import subprocess
from pathlib import Path

from meute.cli.tmux_env import meute_command

SHADOWED = ("typer", "anyio", "pydantic")


def plant_packages(folder: Path, marker: Path) -> None:
    """Put in `folder` packages named like meute's dependencies that write `marker` on import."""
    for name in SHADOWED:
        package = folder / name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(
            f"open({str(marker)!r}, 'a').write({name!r})\n", encoding="utf-8"
        )


def pinned_env(root: Path) -> dict[str, str]:
    return {
        "HOME": str(root / "home"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_STATE_HOME": str(root / "state"),
    }


def test_a_planted_package_in_the_current_folder_is_not_imported(tmp_path: Path) -> None:
    folder = tmp_path / "repo"
    marker = tmp_path / "shadowed.txt"
    plant_packages(folder, marker)
    result = subprocess.run(
        [*meute_command(), "mcp", "--help"],
        cwd=folder,
        capture_output=True,
        text=True,
        env=pinned_env(tmp_path),
        check=False,
    )
    assert not marker.exists()
    assert (result.returncode, result.stderr) == (0, "")
