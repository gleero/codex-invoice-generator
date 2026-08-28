from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

BOOTSTRAP_PATH = Path(__file__).resolve().parent.parent / "scripts" / "invoice.py"
SPEC = importlib.util.spec_from_file_location("invoice_bootstrap", BOOTSTRAP_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load bootstrap module from {BOOTSTRAP_PATH}")
bootstrap: Any = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def test_matching_runtime_fingerprint_skips_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    monkeypatch.setattr(bootstrap, "_python", lambda: python)
    monkeypatch.setattr(bootstrap, "runtime_fingerprint", lambda: "current")
    monkeypatch.setattr(bootstrap, "_read_state", lambda: {"fingerprint": "current"})

    def unexpected_install(*_: object, **__: object) -> None:
        raise AssertionError("matching fingerprint must not invoke pip")

    monkeypatch.setattr(bootstrap.subprocess, "run", unexpected_install)
    assert bootstrap.ensure_runtime() == "current"
