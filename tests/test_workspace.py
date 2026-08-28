from __future__ import annotations

import json
from pathlib import Path

import pytest

from invoice_generator.models import InvoiceError
from invoice_generator.workspace import (
    initialize_workspace,
    probe_workspace,
    repair_workspace,
    workspace_status,
)


def test_init_requires_confirmation_and_nonempty_confirmation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    with pytest.raises(InvoiceError, match="explicit confirmation"):
        initialize_workspace(workspace, confirmed=False, allow_nonempty=False)
    assert not workspace.exists()
    workspace.mkdir()
    (workspace / "notes.md").write_text("keep", encoding="utf-8")
    with pytest.raises(InvoiceError, match="not empty"):
        initialize_workspace(workspace, confirmed=True, allow_nonempty=False)
    assert not (workspace / ".invoice-gen").exists()
    marker = initialize_workspace(workspace, confirmed=True, allow_nonempty=True)
    assert marker["status"]["owner"] == "incomplete"
    assert (workspace / "notes.md").read_text(encoding="utf-8") == "keep"


def test_init_is_idempotent_and_workspace_contains_no_code(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    first = initialize_workspace(workspace, confirmed=True, allow_nonempty=False)
    second = initialize_workspace(workspace, confirmed=True, allow_nonempty=False)
    assert first["workspace_id"] == second["workspace_id"]
    assert not (workspace / ".venv").exists()
    assert not (workspace / "invoice_generator").exists()
    assert probe_workspace(workspace).state == "initialized"


def test_corrupt_marker_requires_repair_and_creates_backup(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    initialize_workspace(workspace, confirmed=True, allow_nonempty=False)
    marker = workspace / ".invoice-gen"
    marker.write_text("{broken", encoding="utf-8")
    assert probe_workspace(workspace).state == "corrupt"
    with pytest.raises(InvoiceError, match="confirmation"):
        repair_workspace(workspace, confirmed=False)
    repaired = repair_workspace(workspace, confirmed=True)
    assert repaired["schema_version"] == 1
    assert list(workspace.glob(".invoice-gen.bak-*"))

    marker.write_text('{"schema_version": 1}\n', encoding="utf-8")
    assert probe_workspace(workspace).state == "corrupt"


def test_status_refreshes_stale_fingerprint(workspace_root: Path) -> None:
    marker_path = workspace_root / ".invoice-gen"
    before = json.loads(marker_path.read_text(encoding="utf-8"))
    owner = workspace_root / "data" / "owner.md"
    owner.write_text(owner.read_text(encoding="utf-8").replace("Test Owner", "Changed Owner"), encoding="utf-8")
    after = workspace_status(workspace_root)
    assert after["fingerprints"]["owner"] != before["fingerprints"]["owner"]
    assert after["status"]["owner"] == "ready"

    client = workspace_root / "data" / "clients" / "AE.md"
    before_client = after["fingerprints"]["clients"]["AE.md"]
    changed = client.read_text(encoding="utf-8").replace("Company Number", "Registration Number")
    client.write_text(changed, encoding="utf-8")
    refreshed = workspace_status(workspace_root)
    assert refreshed["fingerprints"]["clients"]["AE.md"] != before_client
