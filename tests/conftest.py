from __future__ import annotations

from pathlib import Path

import pytest

from invoice_generator.workspace import initialize_workspace, refresh_marker

PROJECT_ROOT = Path(__file__).resolve().parent.parent

OWNER = """---
role: "Individual Entrepreneur"
name: "Test Owner"
address: "1 Owner Street, Tbilisi, Georgia"
timezone: "Asia/Tbilisi"
currencies:
  EUR:
    minor_units: 2
    decimal_separator: ","
    group_separator: "."
    display_token: "€"
    token_position: "after"
    space_between: true
    payment_rows:
      - {label: "Intermediary Bank", value: "Example Euro Bank, Frankfurt; SWIFT: EXAMEU22"}
      - {label: "Beneficiary Bank", value: "Example Beneficiary Bank; SWIFT: EXAMGE22"}
      - {label: "Beneficiary", value: "I/E TEST OWNER"}
      - {label: "Account", value: "GE00TESTEUR"}
  USD:
    minor_units: 2
    decimal_separator: ","
    group_separator: "."
    display_token: "$"
    token_position: "before"
    space_between: true
    payment_rows:
      - {label: "Intermediary Bank", value: "Example Dollar Bank, New York; SWIFT: EXAMUS22"}
      - {label: "Beneficiary Bank", value: "Example Beneficiary Bank; SWIFT: EXAMGE22"}
      - {label: "Beneficiary", value: "I/E TEST OWNER"}
      - {label: "Account", value: "GE00TESTUSD"}
  GEL:
    minor_units: 2
    decimal_separator: "."
    group_separator: ","
    display_token: "₾"
    token_position: "after"
    space_between: true
    payment_rows:
      - {label: "Beneficiary Bank", value: "Example Beneficiary Bank; SWIFT: EXAMGE22"}
      - {label: "Beneficiary", value: "I/E TEST OWNER"}
      - {label: "Account", value: "GE00TESTGEL"}
---

# Owner
"""

CLIENT_AE = """---
alias: "AE"
legal_name: "Acme Example Ltd"
address_lines:
  - "42 Example Road, London, United Kingdom"
detail_lines:
  - "Company Number: 00000001; billing@example.test"
first_invoice_number: 1
---

# Client
"""

CLIENT_WG = """---
alias: "WG"
legal_name: "Widget Group Ltd"
address_lines:
  - "7 Sample Avenue, Warsaw, Poland"
detail_lines:
  - "Registration Number: 00000002"
first_invoice_number: 7
---

# Client
"""


@pytest.fixture
def skill_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    workspace = tmp_path / "invoice-workspace"
    initialize_workspace(workspace, confirmed=True, allow_nonempty=False)
    (workspace / "data" / "owner.md").write_text(OWNER, encoding="utf-8")
    (workspace / "data" / "clients" / "AE.md").write_text(CLIENT_AE, encoding="utf-8")
    (workspace / "data" / "clients" / "WG.md").write_text(CLIENT_WG, encoding="utf-8")
    refresh_marker(workspace)
    return workspace
