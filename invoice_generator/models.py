from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InvoiceError(ValueError):
    """An actionable data, layout, or consistency error."""


DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
    }
)
CURRENCY_CODE_RE = re.compile(r"[A-Z][A-Z0-9]{2,7}")


def normalize_dashes(value: str) -> str:
    return value.translate(DASH_TRANSLATION)


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvoiceError(f"Missing or empty field: {field}")
    return value.strip()


def _text_list(value: Any, field: str, *, required: bool) -> tuple[str, ...]:
    if value is None and not required:
        return ()
    if not isinstance(value, list):
        raise InvoiceError(f"{field} must be a YAML list")
    result = tuple(_required_text(item, field) for item in value)
    if required and not result:
        raise InvoiceError(f"{field} must contain at least one line")
    return result


@dataclass(frozen=True)
class PaymentRow:
    label: str
    value: str

    @classmethod
    def from_mapping(cls, value: Any, field: str) -> PaymentRow:
        if not isinstance(value, dict):
            raise InvoiceError(f"{field} must be a YAML mapping")
        return cls(
            label=_required_text(value.get("label"), f"{field}.label"),
            value=_required_text(value.get("value"), f"{field}.value"),
        )


def _legacy_payment_rows(value: dict[str, Any], field: str) -> tuple[PaymentRow, ...] | None:
    names = (
        "intermediary_bank",
        "intermediary_swift",
        "beneficiary_bank",
        "beneficiary_swift",
        "beneficiary_bank_address",
        "beneficiary",
        "account",
    )
    if not set(names).intersection(value):
        return None
    required = {name: _required_text(value.get(name), f"{field}.{name}") for name in names}
    return (
        PaymentRow(
            "Intermediary Bank",
            f"{required['intermediary_bank']}; SWIFT: {required['intermediary_swift']}",
        ),
        PaymentRow(
            "Beneficiary Bank",
            f"{required['beneficiary_bank']}, SWIFT: {required['beneficiary_swift']}; "
            f"{required['beneficiary_bank_address']}",
        ),
        PaymentRow("Beneficiary", required["beneficiary"]),
        PaymentRow("Account", required["account"]),
    )


@dataclass(frozen=True)
class CurrencyProfile:
    code: str
    minor_units: int
    decimal_separator: str
    group_separator: str
    display_token: str
    token_position: str
    space_between: bool
    payment_rows: tuple[PaymentRow, ...]

    @classmethod
    def from_mapping(cls, code: str, value: Any, field: str) -> CurrencyProfile:
        normalized_code = code.strip().upper()
        if not CURRENCY_CODE_RE.fullmatch(normalized_code):
            raise InvoiceError(f"Invalid currency code: {code}")
        if not isinstance(value, dict):
            raise InvoiceError(f"{field} must be a YAML mapping")

        preset = {
            "EUR": {"token": "€", "position": "after", "decimal": ",", "group": ".", "minor": 2},
            "USD": {"token": "$", "position": "before", "decimal": ",", "group": ".", "minor": 2},
        }.get(
            normalized_code,
            {
                "token": normalized_code,
                "position": "after",
                "decimal": ".",
                "group": ",",
                "minor": 2,
            },
        )
        minor_units = value.get("minor_units", preset["minor"])
        if not isinstance(minor_units, int) or isinstance(minor_units, bool) or not 0 <= minor_units <= 4:
            raise InvoiceError(f"{field}.minor_units must be an integer from 0 to 4")
        decimal_separator = value.get("decimal_separator", preset["decimal"])
        group_separator = value.get("group_separator", preset["group"])
        if not isinstance(decimal_separator, str) or len(decimal_separator) != 1:
            raise InvoiceError(f"{field}.decimal_separator must be one character")
        if not isinstance(group_separator, str) or len(group_separator) > 1:
            raise InvoiceError(f"{field}.group_separator must be empty or one character")
        if group_separator == decimal_separator:
            raise InvoiceError(f"{field} decimal and group separators must differ")
        token_position = value.get("token_position", preset["position"])
        if token_position not in {"before", "after"}:
            raise InvoiceError(f"{field}.token_position must be before or after")
        space_between = value.get("space_between", True)
        if not isinstance(space_between, bool):
            raise InvoiceError(f"{field}.space_between must be true or false")

        raw_rows = value.get("payment_rows")
        legacy_rows = _legacy_payment_rows(value, field)
        if raw_rows is None and legacy_rows is not None:
            payment_rows = legacy_rows
        else:
            if not isinstance(raw_rows, list) or not 1 <= len(raw_rows) <= 4:
                raise InvoiceError(f"{field}.payment_rows must contain 1 to 4 rows")
            payment_rows = tuple(
                PaymentRow.from_mapping(row, f"{field}.payment_rows[{index}]") for index, row in enumerate(raw_rows)
            )
        return cls(
            code=normalized_code,
            minor_units=minor_units,
            decimal_separator=decimal_separator,
            group_separator=group_separator,
            display_token=_required_text(value.get("display_token", preset["token"]), f"{field}.display_token"),
            token_position=token_position,
            space_between=space_between,
            payment_rows=payment_rows,
        )


@dataclass(frozen=True)
class OwnerProfile:
    role: str
    name: str
    address: str
    timezone: str
    currencies: dict[str, CurrencyProfile]

    @classmethod
    def from_mapping(cls, value: Any) -> OwnerProfile:
        if not isinstance(value, dict):
            raise InvoiceError("Owner frontmatter must be a YAML mapping")
        timezone = _required_text(value.get("timezone"), "timezone")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise InvoiceError(f"Unknown IANA timezone: {timezone}") from exc
        raw_currencies = value.get("currencies")
        if not isinstance(raw_currencies, dict) or not raw_currencies:
            raise InvoiceError("currencies must contain at least one configured currency")
        currencies: dict[str, CurrencyProfile] = {}
        for raw_code, raw_profile in raw_currencies.items():
            if not isinstance(raw_code, str):
                raise InvoiceError("currency codes must be strings")
            profile = CurrencyProfile.from_mapping(raw_code, raw_profile, f"currencies.{raw_code}")
            if profile.code in currencies:
                raise InvoiceError(f"Duplicate currency code: {profile.code}")
            currencies[profile.code] = profile
        return cls(
            role=_required_text(value.get("role"), "role"),
            name=_required_text(value.get("name"), "name"),
            address=_required_text(value.get("address"), "address"),
            timezone=timezone,
            currencies=currencies,
        )


@dataclass(frozen=True)
class ClientProfile:
    alias: str
    legal_name: str
    address_lines: tuple[str, ...]
    detail_lines: tuple[str, ...]
    first_invoice_number: int

    @classmethod
    def from_mapping(cls, value: Any) -> ClientProfile:
        if not isinstance(value, dict):
            raise InvoiceError("Client frontmatter must be a YAML mapping")
        alias = _required_text(value.get("alias"), "alias").upper()
        if not re.fullmatch(r"[A-Z]{2,3}", alias):
            raise InvoiceError("alias must contain 2-3 uppercase ASCII letters")
        first_number = value.get("first_invoice_number", 1)
        if not isinstance(first_number, int) or isinstance(first_number, bool) or first_number < 1:
            raise InvoiceError("first_invoice_number must be a positive integer")
        return cls(
            alias=alias,
            legal_name=_required_text(value.get("legal_name"), "legal_name"),
            address_lines=_text_list(value.get("address_lines"), "address_lines", required=True),
            detail_lines=_text_list(value.get("detail_lines", []), "detail_lines", required=False),
            first_invoice_number=first_number,
        )


@dataclass(frozen=True)
class InvoiceRequest:
    client: ClientProfile
    amount: Decimal
    currency: str
    description: str
    issue_date: date
    period: str | None = None

    @classmethod
    def create(
        cls,
        *,
        client: ClientProfile,
        amount: str | Decimal,
        currency: str,
        description: str,
        issue_date: date,
        period: str | None = None,
    ) -> InvoiceRequest:
        try:
            decimal_amount = Decimal(str(amount))
        except (InvalidOperation, ValueError) as exc:
            raise InvoiceError(f"Invalid decimal amount: {amount}") from exc
        if not decimal_amount.is_finite() or decimal_amount <= 0:
            raise InvoiceError("Amount must be a positive finite decimal")
        normalized_currency = currency.strip().upper()
        if not CURRENCY_CODE_RE.fullmatch(normalized_currency):
            raise InvoiceError("Currency must be a 3-8 character uppercase code")
        normalized_period = normalize_dashes(period.strip()) if period and period.strip() else None
        return cls(
            client=client,
            amount=decimal_amount,
            currency=normalized_currency,
            description=normalize_dashes(_required_text(description, "description")),
            issue_date=issue_date,
            period=normalized_period,
        )
