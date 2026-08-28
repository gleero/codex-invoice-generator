from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import fitz
import pytest

from invoice_generator.models import CurrencyProfile, InvoiceError, InvoiceRequest
from invoice_generator.pdf import format_money
from invoice_generator.profiles import find_client, load_owner
from invoice_generator.service import (
    default_issue_date,
    issue_invoice,
    next_sequence,
    validate_generated_pdf,
    validate_ledger,
    validate_repository,
)


def make_request(workspace: Path, alias: str, *, currency: str = "EUR", amount: str = "445") -> InvoiceRequest:
    return InvoiceRequest.create(
        client=find_client(workspace, alias),
        amount=amount,
        currency=currency,
        description="Professional software development services",
        issue_date=date(2026, 8, 28),
    )


def pdf_text(path: Path) -> str:
    document = fitz.open(path)
    try:
        page: Any = document[0]
        return page.get_text()
    finally:
        document.close()


def test_money_formatting_for_presets_and_generic_currency(workspace_root: Path) -> None:
    owner = load_owner(workspace_root)
    assert format_money(Decimal("1500.00"), owner.currencies["EUR"]) == "1.500,00 €"
    assert format_money(Decimal("1500.00"), owner.currencies["USD"]) == "$ 1.500,00"
    assert format_money(Decimal("4500"), owner.currencies["GEL"]) == "4,500.00 ₾"
    jpy = CurrencyProfile.from_mapping(
        "JPY",
        {
            "minor_units": 0,
            "display_token": "JPY",
            "token_position": "before",
            "space_between": True,
            "payment_rows": [{"label": "Account", "value": "JP123"}],
        },
        "currencies.JPY",
    )
    assert format_money(Decimal("4500.4"), jpy) == "JPY 4,500"


def test_independent_custom_numbering_and_bank_selection(workspace_root: Path) -> None:
    ae_001 = issue_invoice(workspace_root, make_request(workspace_root, "AE"))
    ae_002 = issue_invoice(workspace_root, make_request(workspace_root, "AE", amount="500"))
    wg_007 = issue_invoice(workspace_root, make_request(workspace_root, "WG", currency="USD", amount="1500"))
    assert [ae_001.name, ae_002.name, wg_007.name] == ["AE-001.pdf", "AE-002.pdf", "WG-007.pdf"]
    assert "Example Euro Bank" in pdf_text(ae_001)
    assert "Example Dollar Bank" in pdf_text(wg_007)


def test_first_invoice_number_is_a_floor_for_existing_alias() -> None:
    ledger = "| KNN-001 | 2026-05-07 | KNN | Legacy payer | EUR | 5000.00 | Service | | legacy.pdf |\n"
    assert next_sequence(ledger, "KNN", first_invoice_number=3) == 3
    assert next_sequence(ledger + "| KNN-004 |", "KNN", first_invoice_number=3) == 5


def test_period_is_directly_below_activity(workspace_root: Path) -> None:
    request = InvoiceRequest.create(
        client=find_client(workspace_root, "AE"),
        amount="5000",
        currency="EUR",
        description="Software Development and Consulting Services",
        period="20 Jul - 16 Aug",
        issue_date=date(2026, 8, 28),
    )
    path = issue_invoice(workspace_root, request)
    document = fitz.open(path)
    try:
        page: Any = document[0]
        activity = page.search_for("Software Development and Consulting Services")[0]
        period = page.search_for("Period: 20 Jul - 16 Aug")[0]
        assert 2 <= period.y0 - activity.y1 <= 8
    finally:
        document.close()


def test_generic_currency_pdf_is_one_page_a4(workspace_root: Path) -> None:
    path = issue_invoice(workspace_root, make_request(workspace_root, "AE", currency="GEL", amount="4500"))
    owner = load_owner(workspace_root)
    validate_generated_pdf(path, invoice_id="AE-001", legal_name="Acme Example Ltd", owner=owner, currency="GEL")
    document = fitz.open(path)
    try:
        assert document.page_count == 1
        assert document[0].rect.width == pytest.approx(595.276, abs=0.5)
        assert document[0].rect.height == pytest.approx(841.89, abs=0.5)
        drawings = document[0].get_drawings()
        colored = [item["rect"] for item in drawings if item.get("fill") is not None]
        assert any(rect.x0 == pytest.approx(56.69, abs=0.5) for rect in colored)
        page: Any = document[0]
        assert "4,500.00 ₾" in page.get_text()
    finally:
        document.close()


def test_amount_is_rounded_to_currency_minor_units(workspace_root: Path) -> None:
    path = issue_invoice(workspace_root, make_request(workspace_root, "AE", amount="1.239"))
    assert "1,24 €" in pdf_text(path)
    ledger = (workspace_root / "data" / "invoices.md").read_text(encoding="utf-8")
    assert "| EUR | 1.24 |" in ledger

    tiny = make_request(workspace_root, "WG", amount="0.001")
    before = (workspace_root / "data" / "invoices.md").read_text(encoding="utf-8")
    with pytest.raises(InvoiceError, match="rounds to zero"):
        issue_invoice(workspace_root, tiny)
    assert (workspace_root / "data" / "invoices.md").read_text(encoding="utf-8") == before


def test_existing_output_is_never_overwritten(workspace_root: Path) -> None:
    path = issue_invoice(workspace_root, make_request(workspace_root, "AE"))
    ledger = workspace_root / "data" / "invoices.md"
    lines = ledger.read_text(encoding="utf-8").splitlines()
    ledger.write_text("\n".join(line for line in lines if "| AE-001 |" not in line) + "\n", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(InvoiceError, match="Refusing to overwrite"):
        issue_invoice(workspace_root, make_request(workspace_root, "AE"))
    assert path.read_bytes() == before


def test_failed_render_does_not_change_ledger(workspace_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = workspace_root / "data" / "invoices.md"
    before = ledger.read_text(encoding="utf-8")

    def fail_render(**_: object) -> None:
        raise InvoiceError("intentional render failure")

    monkeypatch.setattr("invoice_generator.service.render_invoice", fail_render)
    with pytest.raises(InvoiceError, match="intentional"):
        issue_invoice(workspace_root, make_request(workspace_root, "AE"))
    assert ledger.read_text(encoding="utf-8") == before
    assert not list((workspace_root / "output").rglob("*.pdf"))


def test_failed_ledger_append_rolls_back_pdf(workspace_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = workspace_root / "data" / "invoices.md"
    before = ledger.read_text(encoding="utf-8")

    def fail_append(*_: object, **__: object) -> None:
        raise OSError("intentional ledger failure")

    monkeypatch.setattr("invoice_generator.service.append_ledger", fail_append)
    with pytest.raises(OSError, match="intentional ledger"):
        issue_invoice(workspace_root, make_request(workspace_root, "AE"))
    assert ledger.read_text(encoding="utf-8") == before
    assert not list((workspace_root / "output").rglob("*.pdf"))


def test_long_content_and_unconfigured_currency_fail_cleanly(workspace_root: Path) -> None:
    request = InvoiceRequest.create(
        client=find_client(workspace_root, "AE"),
        amount="100",
        currency="EUR",
        description="unbreakable" * 80,
        issue_date=date(2026, 8, 28),
    )
    before = (workspace_root / "data" / "invoices.md").read_text(encoding="utf-8")
    with pytest.raises(InvoiceError, match="does not fit"):
        issue_invoice(workspace_root, request)
    with pytest.raises(InvoiceError, match="not configured"):
        issue_invoice(workspace_root, make_request(workspace_root, "AE", currency="GBP"))
    assert (workspace_root / "data" / "invoices.md").read_text(encoding="utf-8") == before


def test_long_payment_row_fails_without_clipping(workspace_root: Path) -> None:
    owner = workspace_root / "data" / "owner.md"
    text = owner.read_text(encoding="utf-8").replace(
        "Example Euro Bank, Frankfurt; SWIFT: EXAMEU22",
        "UNBREAKABLE" * 80,
    )
    owner.write_text(text, encoding="utf-8")
    before = (workspace_root / "data" / "invoices.md").read_text(encoding="utf-8")
    with pytest.raises(InvoiceError, match="too long"):
        issue_invoice(workspace_root, make_request(workspace_root, "AE"))
    assert (workspace_root / "data" / "invoices.md").read_text(encoding="utf-8") == before
    assert not list((workspace_root / "output").rglob("*.pdf"))


def test_invalid_amount_currency_and_dash_normalization(workspace_root: Path) -> None:
    client = find_client(workspace_root, "AE")
    with pytest.raises(InvoiceError, match="positive"):
        InvoiceRequest.create(client=client, amount="0", currency="EUR", description="Service", issue_date=date.today())
    with pytest.raises(InvoiceError, match="3-8"):
        InvoiceRequest.create(client=client, amount="1", currency="?", description="Service", issue_date=date.today())
    request = InvoiceRequest.create(
        client=client,
        amount="1",
        currency="eur",
        description="Consulting \u2013 support",
        period="1 Aug 2026 \u2014 31 Aug 2026",
        issue_date=date.today(),
    )
    assert request.currency == "EUR"
    assert request.description == "Consulting - support"
    assert request.period == "1 Aug 2026 - 31 Aug 2026"


def test_repository_and_ledger_validation(workspace_root: Path, tmp_path: Path) -> None:
    assert validate_repository(workspace_root) == (2, 0)
    assert default_issue_date(workspace_root).year >= 2026
    ledger = tmp_path / "ledger.md"
    with pytest.raises(InvoiceError, match="not found"):
        validate_ledger(ledger)
    ledger.write_text("# broken", encoding="utf-8")
    with pytest.raises(InvoiceError, match="invalid header"):
        validate_ledger(ledger)
