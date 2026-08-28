"""Render deterministic, validated, single-page A4 invoice PDFs.

Created by Vladimir Perekladov <gleero@gmail.com>.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .models import CurrencyProfile, InvoiceError, InvoiceRequest, OwnerProfile
from .resources import font_directory

PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT = 56.69
RIGHT = 538.24
TABLE_SPLIT = 423.57

DARK_BLUE = HexColor("#31394D")
BLACK = HexColor("#000000")
BODY_GRAY = HexColor("#5E5E5E")
BANK_GRAY = HexColor("#666666")
TABLE_YELLOW = Color(0.9437051, 0.9063921, 0.7039822)
BALANCE_GRAY = Color(0.942691, 0.942691, 0.942691)


@dataclass(frozen=True)
class FontSet:
    """Registered PDF font names used by the calibrated invoice layout."""

    serif_bold: str
    sans: str
    unicode_sans: str
    heading_bold: str


def register_fonts() -> FontSet:
    """Register bundled fonts and return their stable ReportLab names."""
    font_dir = font_directory()
    required = {
        "InvoiceLiberationSerifBold": font_dir / "LiberationSerif-Bold.ttf",
        "InvoiceLiberationSans": font_dir / "LiberationSans-Regular.ttf",
        "InvoiceNotoSans": font_dir / "NotoSans-Variable.ttf",
        "InvoiceMerriweatherBold": font_dir / "Merriweather-Bold.ttf",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise InvoiceError("Required bundled fonts are missing: " + ", ".join(missing))
    for name, path in required.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    return FontSet(
        serif_bold="InvoiceLiberationSerifBold",
        sans="InvoiceLiberationSans",
        unicode_sans="InvoiceNotoSans",
        heading_bold="InvoiceMerriweatherBold",
    )


def _font_for_text(text: str, primary: str, fallback: str) -> str:
    """Choose a font that contains every non-whitespace character."""
    primary_font: Any = pdfmetrics.getFont(primary)
    face = primary_font.face
    cmap = getattr(face, "charToGlyph", {})
    if all(ord(character) in cmap for character in text if not character.isspace()):
        return primary
    fallback_font: Any = pdfmetrics.getFont(fallback)
    fallback_face = fallback_font.face
    fallback_cmap = getattr(fallback_face, "charToGlyph", {})
    missing = [character for character in text if not character.isspace() and ord(character) not in fallback_cmap]
    if missing:
        rendered = " ".join(f"U+{ord(character):04X}" for character in sorted(set(missing)))
        raise InvoiceError(f"Bundled fonts cannot render: {rendered}")
    return fallback


def format_number(amount: Decimal, currency: CurrencyProfile) -> str:
    """Format a decimal using the currency's precision and separators."""
    quantizer = Decimal(1).scaleb(-currency.minor_units)
    rounded = amount.quantize(quantizer)
    western = f"{rounded:,.{currency.minor_units}f}"
    integer, dot, fraction = western.partition(".")
    if currency.group_separator != ",":
        integer = integer.replace(",", currency.group_separator)
    if currency.minor_units:
        return integer + currency.decimal_separator + fraction
    return integer


def format_money(amount: Decimal, currency: CurrencyProfile) -> str:
    """Format an amount with its configured currency token and spacing."""
    number = format_number(amount, currency)
    separator = " " if currency.space_between else ""
    if currency.token_position == "before":
        return f"{currency.display_token}{separator}{number}"
    return f"{number}{separator}{currency.display_token}"


def _text_width(text: str, font: str, size: float) -> float:
    """Measure text with the exact metrics used for PDF rendering."""
    return pdfmetrics.stringWidth(text, font, size)


def _fit_single_line(text: str, font: str, start_size: float, min_size: float, max_width: float) -> float:
    """Find the largest allowed size that keeps text on one line."""
    size = start_size
    while size >= min_size:
        if _text_width(text, font, size) <= max_width:
            return round(size, 2)
        size -= 0.25
    raise InvoiceError(f"Text is too long for the invoice layout: {text}")


def _wrap_one(text: str, font: str, size: float, max_width: float) -> list[str] | None:
    """Wrap one paragraph by words, returning ``None`` for unbreakable overflow."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    if _text_width(current, font, size) > max_width:
        return None
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(candidate, font, size) <= max_width:
            current = candidate
        else:
            if _text_width(word, font, size) > max_width:
                return None
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_wrapped(
    paragraphs: list[str],
    font: str,
    start_size: float,
    min_size: float,
    max_width: float,
    max_lines: int,
) -> tuple[float, list[str]]:
    """Fit paragraphs into a bounded line count by reducing font size."""
    size = start_size
    while size >= min_size:
        lines: list[str] = []
        valid = True
        for paragraph in paragraphs:
            wrapped = _wrap_one(paragraph, font, size, max_width)
            if wrapped is None:
                valid = False
                break
            lines.extend(wrapped)
        if valid and len(lines) <= max_lines:
            return round(size, 2), lines
        size -= 0.25
    label = " / ".join(paragraphs)
    raise InvoiceError(f"Text does not fit on one page: {label}")


def _set_font(canvas: Canvas, font: str, size: float, color=BLACK) -> None:
    """Set font and fill color together for consistent drawing calls."""
    canvas.setFont(font, size)
    canvas.setFillColor(color)


def _draw_right(canvas: Canvas, text: str, x: float, y: float) -> None:
    """Draw text right-aligned to the supplied baseline coordinate."""
    canvas.drawRightString(x, y, text)


def render_invoice(
    *,
    owner: OwnerProfile,
    request: InvoiceRequest,
    invoice_id: str,
    output_path: Path,
) -> None:
    """Render one invoice to ``output_path`` or fail before clipping content."""
    fonts = register_fonts()
    try:
        currency = owner.currencies[request.currency]
    except KeyError as exc:
        configured = ", ".join(sorted(owner.currencies))
        raise InvoiceError(
            f"Currency {request.currency} is not configured in owner.md. Configured: {configured}"
        ) from exc
    money = format_money(request.amount, currency)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # These coordinates are intentionally fixed: they reproduce the reference A4 grid.
    canvas = Canvas(str(output_path), pagesize=A4, pageCompression=1)
    canvas.setTitle(invoice_id)
    canvas.setAuthor(owner.name)
    canvas.setSubject(f"Invoice {invoice_id} for {request.client.legal_name}")

    # Owner header.
    role_font = _font_for_text(owner.role, fonts.serif_bold, fonts.unicode_sans)
    role_size = _fit_single_line(owner.role, role_font, 13, 10, 330)
    _set_font(canvas, role_font, role_size, DARK_BLUE)
    canvas.drawString(LEFT, PAGE_HEIGHT - 70.60, owner.role)
    name_font = _font_for_text(owner.name, fonts.serif_bold, fonts.unicode_sans)
    name_size = _fit_single_line(owner.name, name_font, 18, 13, 330)
    _set_font(canvas, name_font, name_size, DARK_BLUE)
    canvas.drawString(LEFT, PAGE_HEIGHT - 94.39, owner.name)
    address_font = _font_for_text(owner.address, fonts.sans, fonts.unicode_sans)
    address_size = _fit_single_line(owner.address, address_font, 9, 7.5, RIGHT - LEFT)
    _set_font(canvas, address_font, address_size, DARK_BLUE)
    canvas.drawString(LEFT, PAGE_HEIGHT - 116.69, owner.address)

    _set_font(canvas, fonts.heading_bold, 35, BLACK)
    canvas.drawString(LEFT, PAGE_HEIGHT - 199.00, "INVOICE")

    # Billing headings.
    _set_font(canvas, fonts.heading_bold, 12, BLACK)
    canvas.drawString(58.69, PAGE_HEIGHT - 269.30, "BILL TO")
    _draw_right(canvas, f"INVOICE #{invoice_id}", RIGHT - 2, PAGE_HEIGHT - 269.30)

    client_name_font = _font_for_text(request.client.legal_name, fonts.heading_bold, fonts.unicode_sans)
    client_name_size = _fit_single_line(request.client.legal_name, client_name_font, 10, 8, 330)
    _set_font(canvas, client_name_font, client_name_size, DARK_BLUE)
    canvas.drawString(58.69, PAGE_HEIGHT - 316.08, request.client.legal_name)

    detail_paragraphs = list(request.client.address_lines + request.client.detail_lines)
    detail_font = _font_for_text(" ".join(detail_paragraphs), fonts.sans, fonts.unicode_sans)
    detail_size, detail_lines = _fit_wrapped(detail_paragraphs, detail_font, 9, 7.5, 340, 4)
    _set_font(canvas, detail_font, detail_size, DARK_BLUE)
    detail_line_height = max(11.0, detail_size + 3.0)
    for index, line in enumerate(detail_lines):
        canvas.drawString(58.69, PAGE_HEIGHT - (330.38 + index * detail_line_height), line)

    _set_font(canvas, fonts.heading_bold, 12, BLACK)
    _draw_right(canvas, "INVOICE DATE", RIGHT - 2, PAGE_HEIGHT - 317.48)
    _set_font(canvas, fonts.sans, 10, BLACK)
    _draw_right(canvas, request.issue_date.strftime("%d-%m-%Y"), RIGHT - 2, PAGE_HEIGHT - 328.78)

    # Item header.
    canvas.setFillColor(TABLE_YELLOW)
    canvas.rect(LEFT, PAGE_HEIGHT - 431.99, TABLE_SPLIT - LEFT, 35, stroke=0, fill=1)
    canvas.rect(TABLE_SPLIT, PAGE_HEIGHT - 431.99, RIGHT - TABLE_SPLIT, 35, stroke=0, fill=1)
    _set_font(canvas, fonts.heading_bold, 12, BLACK)
    canvas.drawString(66.69, PAGE_HEIGHT - 418.69, "ITEM")
    _draw_right(canvas, "TOTAL", RIGHT - 10, PAGE_HEIGHT - 418.69)

    max_description_lines = 2 if request.period else 3
    description_font = _font_for_text(request.description, fonts.sans, fonts.unicode_sans)
    description_size, description_lines = _fit_wrapped(
        [request.description], description_font, 11, 9, TABLE_SPLIT - 70, max_description_lines
    )
    _set_font(canvas, description_font, description_size, BODY_GRAY)
    description_line_height = max(13.0, description_size + 4.0)
    for index, line in enumerate(description_lines):
        canvas.drawString(60.69, PAGE_HEIGHT - (446.49 + index * description_line_height), line)

    money_font = _font_for_text(money, fonts.sans, fonts.unicode_sans)
    money_size = _fit_single_line(money, money_font, 10, 8, RIGHT - TABLE_SPLIT - 12)
    _set_font(canvas, money_font, money_size, BLACK)
    _draw_right(canvas, money, RIGHT - 4, PAGE_HEIGHT - 445.79)

    if request.period:
        period_text = f"Period: {request.period}"
        period_font = _font_for_text(period_text, fonts.sans, fonts.unicode_sans)
        period_size = _fit_single_line(period_text, period_font, 9, 7.5, TABLE_SPLIT - 70)
        _set_font(canvas, period_font, period_size, BODY_GRAY)
        period_baseline = 446.49 + len(description_lines) * description_line_height
        canvas.drawString(60.69, PAGE_HEIGHT - period_baseline, period_text)

    # Balance row.
    canvas.setFillColor(BALANCE_GRAY)
    canvas.rect(LEFT, PAGE_HEIGHT - 521.77, TABLE_SPLIT - LEFT, 22.73, stroke=0, fill=1)
    canvas.rect(TABLE_SPLIT, PAGE_HEIGHT - 521.77, RIGHT - TABLE_SPLIT, 22.73, stroke=0, fill=1)
    _set_font(canvas, fonts.sans, 10, BLACK)
    canvas.drawString(60.69, PAGE_HEIGHT - 510.84, "Balance Due:")
    _set_font(canvas, money_font, 10, BLACK)
    _draw_right(canvas, money, RIGHT - 4, PAGE_HEIGHT - 510.84)

    # Currency-specific settlement instructions. The four calibrated slots match the reference.
    row_positions = [
        (583.77, 595.77),
        (624.89, 636.89),
        (666.00, 678.00),
        (707.11, 719.11),
    ]
    for row, (label_bottom, value_bottom) in zip(currency.payment_rows, row_positions, strict=False):
        label, value = row.label, row.value
        label_font = _font_for_text(label, fonts.heading_bold, fonts.unicode_sans)
        label_size = _fit_single_line(label, label_font, 11, 9, RIGHT - LEFT)
        _set_font(canvas, label_font, label_size, BANK_GRAY)
        canvas.drawString(LEFT, PAGE_HEIGHT - label_bottom, label)
        value_font = _font_for_text(value, fonts.sans, fonts.unicode_sans)
        value_size = _fit_single_line(value, value_font, 10, 8, RIGHT - LEFT)
        _set_font(canvas, value_font, value_size, BANK_GRAY)
        canvas.drawString(LEFT, PAGE_HEIGHT - value_bottom, value)

    canvas.showPage()
    canvas.save()


def safe_company_directory(name: str) -> str:
    """Convert a legal company name into a portable output directory name."""
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise InvoiceError("Company name cannot be converted to an output directory")
    return cleaned
