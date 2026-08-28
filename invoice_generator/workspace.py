"""Initialize invoice workspaces and maintain their non-sensitive state cache.

Created by Vladimir Perekladov <gleero@gmail.com>.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .models import InvoiceError
from .resources import template_path

MARKER_NAME = ".invoice-gen"
MARKER_SCHEMA_VERSION = 1
IGNORED_EMPTY_ENTRIES = {".DS_Store", "Thumbs.db"}
WORKSPACE_GITIGNORE = """# Private invoice records and generated files.
.invoice-gen
.invoice-gen.bak-*
data/
output/
*.lock
"""


@dataclass(frozen=True)
class WorkspaceProbe:
    """A dependency-light summary of workspace initialization state."""

    state: str
    marker_present: bool
    empty: bool
    entries: tuple[str, ...]
    message: str


def marker_path(workspace: Path) -> Path:
    """Return the hidden marker path for a workspace."""
    return workspace / MARKER_NAME


def _visible_entries(workspace: Path) -> tuple[str, ...]:
    """List entries relevant to the non-empty-folder safety warning."""
    if not workspace.exists():
        return ()
    return tuple(sorted(item.name for item in workspace.iterdir() if item.name not in IGNORED_EMPTY_ENTRIES))


def _read_marker(workspace: Path) -> dict[str, Any]:
    """Load and structurally validate a workspace marker."""
    path = marker_path(workspace)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InvoiceError(f"Workspace is not initialized: {path} is missing") from exc
    except (json.JSONDecodeError, OSError) as exc:
        raise InvoiceError(f"Workspace marker is corrupt: {path}. Run workspace repair after confirmation") from exc
    if not isinstance(value, dict) or value.get("schema_version") != MARKER_SCHEMA_VERSION:
        raise InvoiceError("Workspace marker uses an unsupported schema; run workspace repair after confirmation")
    required = {
        "workspace_id": str,
        "created_at": str,
        "updated_at": str,
        "skill_version": str,
        "runtime_fingerprint": str,
        "status": dict,
        "fingerprints": dict,
    }
    invalid = [key for key, expected in required.items() if not isinstance(value.get(key), expected)]
    if invalid:
        fields = ", ".join(invalid)
        raise InvoiceError(f"Workspace marker is incomplete ({fields}); run workspace repair after confirmation")
    return value


def probe_workspace(workspace: Path) -> WorkspaceProbe:
    """Inspect workspace state without creating or changing files."""
    workspace = workspace.expanduser().resolve()
    entries = _visible_entries(workspace)
    path = marker_path(workspace)
    if not path.exists():
        return WorkspaceProbe(
            state="uninitialized",
            marker_present=False,
            empty=not entries,
            entries=entries[:10],
            message="Current folder is not an Invoice Generator workspace",
        )
    try:
        _read_marker(workspace)
    except InvoiceError as exc:
        return WorkspaceProbe(
            state="corrupt",
            marker_present=True,
            empty=False,
            entries=entries[:10],
            message=str(exc),
        )
    return WorkspaceProbe(
        state="initialized",
        marker_present=True,
        empty=False,
        entries=entries[:10],
        message="Invoice Generator workspace marker is valid",
    )


def _sha256(path: Path) -> str | None:
    """Return a file fingerprint, or ``None`` when the file is absent."""
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _owner_status(workspace: Path) -> str:
    """Return the cached readiness state for ``owner.md``."""
    owner_path = workspace / "data" / "owner.md"
    if not owner_path.is_file():
        return "missing"
    try:
        from .profiles import validate_owner_complete

        validate_owner_complete(workspace)
    except InvoiceError:
        return "incomplete"
    return "ready"


def _ledger_status(workspace: Path) -> str:
    """Return the cached readiness state for the invoice ledger."""
    ledger_path = workspace / "data" / "invoices.md"
    if not ledger_path.is_file():
        return "missing"
    try:
        from .service import validate_ledger

        validate_ledger(ledger_path)
    except InvoiceError:
        return "invalid"
    return "ready"


def _client_fingerprints(workspace: Path) -> dict[str, str]:
    """Fingerprint each client profile without storing its contents."""
    clients_dir = workspace / "data" / "clients"
    if not clients_dir.is_dir():
        return {}
    return {
        path.name: fingerprint
        for path in sorted(clients_dir.glob("*.md"))
        if (fingerprint := _sha256(path)) is not None
    }


def _marker_payload(workspace: Path, *, workspace_id: str, created_at: str) -> dict[str, Any]:
    """Build a privacy-safe marker payload from authoritative Markdown files."""
    clients_dir = workspace / "data" / "clients"
    client_count = len(list(clients_dir.glob("*.md"))) if clients_dir.is_dir() else 0
    now = datetime.now(UTC).isoformat()
    return {
        "schema_version": MARKER_SCHEMA_VERSION,
        "workspace_id": workspace_id,
        "created_at": created_at,
        "updated_at": now,
        "skill_version": __version__,
        "runtime_fingerprint": os.environ.get("INVOICE_RUNTIME_FINGERPRINT", "direct"),
        "status": {
            "owner": _owner_status(workspace),
            "ledger": _ledger_status(workspace),
            "client_count": client_count,
        },
        "fingerprints": {
            "owner": _sha256(workspace / "data" / "owner.md"),
            "ledger": _sha256(workspace / "data" / "invoices.md"),
            "clients": _client_fingerprints(workspace),
        },
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Durably replace a JSON file without exposing a partial marker."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temp_path = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def refresh_marker(workspace: Path) -> dict[str, Any]:
    """Rebuild cached statuses and fingerprints while preserving identity."""
    workspace = workspace.expanduser().resolve()
    current = _read_marker(workspace)
    payload = _marker_payload(
        workspace,
        workspace_id=str(current["workspace_id"]),
        created_at=str(current["created_at"]),
    )
    _atomic_write_json(marker_path(workspace), payload)
    return payload


def initialize_workspace(
    workspace: Path,
    *,
    confirmed: bool,
    allow_nonempty: bool,
) -> dict[str, Any]:
    """Create an idempotent workspace after explicit user confirmation."""
    workspace = workspace.expanduser().resolve()
    if not confirmed:
        raise InvoiceError("Initialization requires explicit confirmation (--confirmed)")
    workspace.mkdir(parents=True, exist_ok=True)
    probe = probe_workspace(workspace)
    if probe.state == "initialized":
        return refresh_marker(workspace)
    if probe.state == "corrupt":
        raise InvoiceError("Marker is corrupt; use workspace repair instead of init")
    if not probe.empty and not allow_nonempty:
        names = ", ".join(probe.entries)
        raise InvoiceError(f"Workspace is not empty ({names}); confirm again with --allow-nonempty")

    clients = workspace / "data" / "clients"
    clients.mkdir(parents=True, exist_ok=True)
    (workspace / "output").mkdir(parents=True, exist_ok=True)
    copies = (
        (template_path("owner.example.md"), workspace / "data" / "owner.md"),
        (template_path("invoices.example.md"), workspace / "data" / "invoices.md"),
    )
    for source, destination in copies:
        if not destination.exists():
            shutil.copyfile(source, destination)
    gitignore = workspace / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(WORKSPACE_GITIGNORE, encoding="utf-8")

    # The marker is written last so a failed setup never appears initialized.
    now = datetime.now(UTC).isoformat()
    payload = _marker_payload(workspace, workspace_id=str(uuid.uuid4()), created_at=now)
    _atomic_write_json(marker_path(workspace), payload)
    return payload


def repair_workspace(workspace: Path, *, confirmed: bool) -> dict[str, Any]:
    """Back up a marker and rebuild it from Markdown after confirmation."""
    workspace = workspace.expanduser().resolve()
    if not confirmed:
        raise InvoiceError("Repair requires explicit confirmation (--confirmed)")
    path = marker_path(workspace)
    if not (workspace / "data" / "invoices.md").is_file():
        raise InvoiceError("Cannot repair marker because data/invoices.md is missing")
    if path.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = workspace / f"{MARKER_NAME}.bak-{stamp}"
        shutil.copyfile(path, backup)
    now = datetime.now(UTC).isoformat()
    payload = _marker_payload(workspace, workspace_id=str(uuid.uuid4()), created_at=now)
    _atomic_write_json(path, payload)
    return payload


def workspace_status(workspace: Path, *, refresh: bool = False) -> dict[str, Any]:
    """Return current state, revalidating only when fingerprints are stale."""
    workspace = workspace.expanduser().resolve()
    marker = refresh_marker(workspace) if refresh else _read_marker(workspace)
    current_owner_hash = _sha256(workspace / "data" / "owner.md")
    current_ledger_hash = _sha256(workspace / "data" / "invoices.md")
    current_client_hashes = _client_fingerprints(workspace)
    fingerprints = marker.get("fingerprints", {})
    stale = (
        fingerprints.get("owner") != current_owner_hash
        or fingerprints.get("ledger") != current_ledger_hash
        or fingerprints.get("clients") != current_client_hashes
        or marker.get("skill_version") != __version__
    )
    # Markdown is authoritative; the marker only avoids repeated full parsing.
    if stale:
        marker = refresh_marker(workspace)
    return marker


def probe_as_dict(probe: WorkspaceProbe) -> dict[str, Any]:
    """Convert a probe result into a JSON-serializable dictionary."""
    return asdict(probe)
