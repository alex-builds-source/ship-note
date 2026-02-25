from __future__ import annotations

from pathlib import Path
import tomllib

from ship_note import __version__


def test_pyproject_version_matches_package_version():
    root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__
