from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from invoice_generator import __version__


def test_version_metadata_stays_synchronized() -> None:
    root = Path(__file__).resolve().parent.parent
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))

    version = project["project"]["version"]
    assert re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version)
    assert project["tool"]["bumpversion"]["current_version"] == version
    assert __version__ == version
    assert package["version"] == version
    assert package_lock["version"] == version
    assert package_lock["packages"][""]["version"] == version
    assert "bump-my-version==1.5.1" in project["project"]["optional-dependencies"]["dev"]
