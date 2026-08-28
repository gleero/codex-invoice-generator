from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageChops, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from invoice_generator.models import InvoiceRequest  # noqa: E402
from invoice_generator.pdf import render_invoice  # noqa: E402
from invoice_generator.profiles import find_client, load_owner  # noqa: E402

FIXTURES = {
    "WG-001": {
        "client": "WG",
        "amount": Decimal("1500.00"),
        "date": date(2026, 4, 1),
        "description": "Development of software for the vending machine monitoring system; Consulting Services.",
        "period": "16 Mar 2026 - 31 Mar 2026",
    },
    "AE-001": {
        "client": "AE",
        "amount": Decimal("445.00"),
        "date": date(2026, 7, 13),
        "description": "SMM Service",
        "period": None,
    },
}


def render_png(pdf_path: Path, png_path: Path) -> None:
    document = fitz.open(pdf_path)
    try:
        page: Any = document[0]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
        pixmap.save(png_path)
    finally:
        document.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=ROOT)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    owner = load_owner(workspace)
    destination = ROOT / "tmp" / "pdfs" / "reference-comparison"
    destination.mkdir(parents=True, exist_ok=True)
    for invoice_id, values in FIXTURES.items():
        source_pdf = ROOT / "sources" / f"{invoice_id}.pdf"
        if not source_pdf.exists():
            raise SystemExit(f"Missing local reference: {source_pdf}")
        client = find_client(workspace, values["client"])
        request = InvoiceRequest.create(
            client=client,
            amount=values["amount"],
            currency="EUR",
            description=values["description"],
            issue_date=values["date"],
            period=values["period"],
        )
        generated_pdf = destination / f"{invoice_id}-generated.pdf"
        reference_png = destination / f"{invoice_id}-reference.png"
        generated_png = destination / f"{invoice_id}-generated.png"
        diff_png = destination / f"{invoice_id}-diff.png"
        render_invoice(
            owner=owner,
            request=request,
            invoice_id=invoice_id,
            output_path=generated_pdf,
        )
        render_png(source_pdf, reference_png)
        render_png(generated_pdf, generated_png)
        reference = Image.open(reference_png).convert("RGB")
        generated = Image.open(generated_png).convert("RGB")
        difference = ImageChops.difference(reference, generated)
        ImageEnhance.Contrast(difference).enhance(4).save(diff_png)
        print(generated_pdf)
        print(diff_png)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
