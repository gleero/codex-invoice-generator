"""Locate bundled fonts and templates in source and wheel installations.

Created by Vladimir Perekladov <gleero@gmail.com>.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .models import InvoiceError

SOURCE_ROOT = Path(__file__).resolve().parent.parent


def _resource_root() -> Path:
    """Return the source checkout or installed data-files root."""
    source_assets = SOURCE_ROOT / "assets" / "fonts"
    if source_assets.is_dir():
        return SOURCE_ROOT
    installed = Path(sys.prefix) / "share" / "invoice-generator"
    if installed.is_dir():
        return installed
    raise InvoiceError("Invoice Generator resources are missing; reinstall the skill environment")


def font_directory() -> Path:
    """Return the directory containing the bundled OFL fonts."""
    return _resource_root() / "assets" / "fonts"


def template_path(name: str) -> Path:
    """Return a validated path to one bundled Markdown template."""
    path = _resource_root() / "templates" / name
    if not path.is_file():
        raise InvoiceError(f"Bundled template is missing: {name}")
    return path
