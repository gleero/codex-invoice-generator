from __future__ import annotations

from datetime import date

import pytest

from invoice_generator.models import ClientProfile, CurrencyProfile, InvoiceError, OwnerProfile, PaymentRow


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        ({"minor_units": 5, "payment_rows": [{"label": "A", "value": "B"}]}, "minor_units"),
        ({"decimal_separator": "..", "payment_rows": [{"label": "A", "value": "B"}]}, "decimal_separator"),
        ({"group_separator": "..", "payment_rows": [{"label": "A", "value": "B"}]}, "group_separator"),
        (
            {"decimal_separator": ".", "group_separator": ".", "payment_rows": [{"label": "A", "value": "B"}]},
            "must differ",
        ),
        ({"token_position": "middle", "payment_rows": [{"label": "A", "value": "B"}]}, "token_position"),
        ({"space_between": "yes", "payment_rows": [{"label": "A", "value": "B"}]}, "space_between"),
        ({"payment_rows": []}, "1 to 4"),
    ],
)
def test_currency_validation(mapping: dict[str, object], message: str) -> None:
    with pytest.raises(InvoiceError, match=message):
        CurrencyProfile.from_mapping("ABC", mapping, "currencies.ABC")


def test_legacy_currency_shape_is_normalized() -> None:
    profile = CurrencyProfile.from_mapping(
        "USD",
        {
            "intermediary_bank": "Example Correspondent Bank",
            "intermediary_swift": "EXAMUS22",
            "beneficiary_bank": "Bank",
            "beneficiary_swift": "BANKXX",
            "beneficiary_bank_address": "Address",
            "beneficiary": "Owner",
            "account": "Account",
        },
        "currencies.USD",
    )
    assert profile.payment_rows[0] == PaymentRow("Intermediary Bank", "Example Correspondent Bank; SWIFT: EXAMUS22")


def test_owner_client_and_payment_validation() -> None:
    with pytest.raises(InvoiceError, match="at least one"):
        OwnerProfile.from_mapping({"role": "R", "name": "N", "address": "A", "timezone": "UTC", "currencies": {}})
    with pytest.raises(InvoiceError, match="Unknown IANA"):
        OwnerProfile.from_mapping(
            {"role": "R", "name": "N", "address": "A", "timezone": "Mars/Base", "currencies": {"USD": {}}}
        )
    with pytest.raises(InvoiceError, match="positive"):
        ClientProfile.from_mapping(
            {
                "alias": "AB",
                "legal_name": "Name",
                "address_lines": ["Address"],
                "first_invoice_number": 0,
            }
        )
    with pytest.raises(InvoiceError, match="mapping"):
        PaymentRow.from_mapping("bad", "row")


def test_date_type_is_available_for_pyright() -> None:
    assert date.fromisoformat("2026-08-28").year == 2026
