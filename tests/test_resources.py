from __future__ import annotations

from pathlib import Path

import pytest

from invoice_generator import resources
from invoice_generator.models import InvoiceError


def test_installed_resource_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    installed = tmp_path / "prefix" / "share" / "invoice-generator"
    fonts = installed / "assets" / "fonts"
    templates = installed / "templates"
    fonts.mkdir(parents=True)
    templates.mkdir(parents=True)
    (templates / "owner.example.md").write_text("example", encoding="utf-8")
    monkeypatch.setattr(resources, "SOURCE_ROOT", source)
    monkeypatch.setattr(resources.sys, "prefix", str(tmp_path / "prefix"))
    assert resources.font_directory() == fonts
    assert resources.template_path("owner.example.md").read_text(encoding="utf-8") == "example"
    with pytest.raises(InvoiceError, match="template is missing"):
        resources.template_path("missing.md")


def test_missing_resource_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resources, "SOURCE_ROOT", tmp_path / "source")
    monkeypatch.setattr(resources.sys, "prefix", str(tmp_path / "prefix"))
    with pytest.raises(InvoiceError, match="resources are missing"):
        resources.font_directory()
