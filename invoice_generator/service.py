"""Coordinate numbering, PDF validation, and transactional invoice issuance.

Created by Vladimir Perekladov <gleero@gmail.com>.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import fitz
from filelock import FileLock

from .models import InvoiceError, InvoiceRequest, OwnerProfile
from .pdf import PAGE_HEIGHT, PAGE_WIDTH, render_invoice, safe_company_directory
from .profiles import load_clients, validate_owner_complete

LEDGER_HEADER = (
    "# Invoice ledger\n\n"
    "| Invoice | Date | Client | Legal Name | Currency | Amount | Description | Period | PDF |\n"
    "| --- | --- | --- | --- | --- | ---: | --- | --- | --- |\n"
)


def _escape_cell(value: str) -> str:
    """Escape user text for a single Markdown table cell."""
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def _ledger_path(workspace: Path) -> Path:
    """Return the canonical invoice ledger path for a workspace."""
    return workspace / "data" / "invoices.md"


def validate_ledger(path: Path) -> str:
    """Read the ledger and verify its identifying table header."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InvoiceError(f"Invoice ledger not found: {path}. Initialize this workspace first") from exc
    if "| Invoice | Date | Client |" not in text:
        raise InvoiceError(f"Invoice ledger has an invalid header: {path}")
    return text


def next_sequence(ledger_text: str, alias: str, first_invoice_number: int = 1) -> int:
    """Return the next sequence for one alias, respecting its configured start."""
    matches = re.findall(rf"(?<![A-Z0-9]){re.escape(alias)}-(\d{{3,}})(?!\d)", ledger_text)
    next_after_ledger = max((int(value) for value in matches), default=0) + 1
    return max(first_invoice_number, next_after_ledger)


def validate_generated_pdf(
    path: Path,
    *,
    invoice_id: str,
    legal_name: str,
    owner: OwnerProfile | None = None,
    currency: str | None = None,
) -> None:
    """Verify page count, geometry, required text, and renderability."""
    try:
        document = fitz.open(path)
    except Exception as exc:
        raise InvoiceError(f"Generated PDF cannot be reopened: {exc}") from exc
    try:
        if document.page_count != 1:
            raise InvoiceError(f"Generated invoice must have one page, got {document.page_count}")
        page: Any = document[0]
        if abs(page.rect.width - PAGE_WIDTH) > 0.5 or abs(page.rect.height - PAGE_HEIGHT) > 0.5:
            raise InvoiceError(f"Generated invoice is not A4: {page.rect}")
        text = page.get_text()
        required = ["INVOICE", invoice_id, legal_name, "Balance Due"]
        if owner is not None and currency is not None:
            required.extend(row.label for row in owner.currencies[currency].payment_rows)
        for expected in required:
            if expected not in text:
                raise InvoiceError(f"Generated PDF is missing expected text: {expected}")
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        if pixmap.width < 590 or pixmap.height < 840:
            raise InvoiceError("Generated PDF did not render at the expected size")
    finally:
        document.close()


def append_ledger(
    path: Path,
    *,
    invoice_id: str,
    request: InvoiceRequest,
    relative_pdf: str,
) -> None:
    """Append and durably flush one invoice row to the Markdown ledger."""
    row = (
        "| "
        + " | ".join(
            [
                invoice_id,
                request.issue_date.isoformat(),
                request.client.alias,
                _escape_cell(request.client.legal_name),
                request.currency,
                format(request.amount, "f"),
                _escape_cell(request.description),
                _escape_cell(request.period or ""),
                _escape_cell(relative_pdf),
            ]
        )
        + " |\n"
    )
    with path.open("a", encoding="utf-8", newline="") as stream:
        stream.write(row)
        stream.flush()
        os.fsync(stream.fileno())


def issue_invoice(workspace: Path, request: InvoiceRequest) -> Path:
    """Issue, validate, and record an invoice as one rollback-safe operation."""
    workspace = workspace.expanduser().resolve()
    ledger = _ledger_path(workspace)
    lock = FileLock(str(ledger) + ".lock", timeout=15)
    # The ledger lock serializes number allocation across concurrent Codex runs.
    with lock:
        ledger_text = validate_ledger(ledger)
        sequence = next_sequence(
            ledger_text,
            request.client.alias,
            request.client.first_invoice_number,
        )
        invoice_id = f"{request.client.alias}-{sequence:03d}"
        company_dir = safe_company_directory(request.client.legal_name)
        final_path = workspace / "output" / company_dir / f"{invoice_id}.pdf"
        if final_path.exists():
            raise InvoiceError(
                f"Refusing to overwrite existing invoice {final_path}. Repair the ledger/output mismatch first."
            )
        final_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f".{invoice_id}-", suffix=".tmp.pdf", dir=final_path.parent, delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            owner = validate_owner_complete(workspace)
            if request.currency not in owner.currencies:
                configured = ", ".join(sorted(owner.currencies))
                raise InvoiceError(
                    f"Currency {request.currency} is not configured in owner.md. Configured: {configured}"
                )
            currency = owner.currencies[request.currency]
            quantizer = Decimal(1).scaleb(-currency.minor_units)
            rounded_amount = request.amount.quantize(quantizer)
            if rounded_amount <= 0:
                raise InvoiceError(f"Amount rounds to zero in {request.currency}")
            request = replace(request, amount=rounded_amount)
            render_invoice(
                owner=owner,
                request=request,
                invoice_id=invoice_id,
                output_path=temp_path,
            )
            validate_generated_pdf(
                temp_path,
                invoice_id=invoice_id,
                legal_name=request.client.legal_name,
                owner=owner,
                currency=request.currency,
            )
            # Publish only a verified PDF; roll it back if the durable ledger write fails.
            os.replace(temp_path, final_path)
            try:
                relative_pdf = final_path.relative_to(workspace).as_posix()
                append_ledger(
                    ledger,
                    invoice_id=invoice_id,
                    request=request,
                    relative_pdf=relative_pdf,
                )
            except Exception:
                final_path.unlink(missing_ok=True)
                raise
        finally:
            temp_path.unlink(missing_ok=True)
        try:
            from .workspace import refresh_marker

            refresh_marker(workspace)
        except InvoiceError:
            pass
        return final_path.resolve()


def default_issue_date(workspace: Path) -> date:
    """Return today's date in the owner's configured timezone."""
    owner = validate_owner_complete(workspace)
    return datetime.now(ZoneInfo(owner.timezone)).date()


def validate_repository(workspace: Path) -> tuple[int, int]:
    """Validate all Markdown data and return client and invoice counts."""
    validate_owner_complete(workspace)
    clients = load_clients(workspace)
    ledger = validate_ledger(_ledger_path(workspace))
    invoice_count = len(re.findall(r"^\| [A-Z]{2,3}-\d{3,} ", ledger, re.MULTILINE))
    return len(clients), invoice_count
