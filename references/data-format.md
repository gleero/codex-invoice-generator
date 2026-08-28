# Workspace data format

All private operational records live under the user's workspace. YAML frontmatter is the source of truth; the Markdown body is explanatory.

## Marker

`.invoice-gen` is a generated JSON cache. It contains schema and skill versions, a random workspace ID, readiness statuses, and file fingerprints. It contains no bank details or absolute paths. Do not edit it manually.

## Owner

`data/owner.md` contains common owner fields and one or more currency profiles:

```yaml
---
role: "Individual Entrepreneur"
name: "Jane Example"
address: "1 Example Street, Tbilisi, Georgia"
timezone: "Asia/Tbilisi"
currencies:
  GEL:
    minor_units: 2
    decimal_separator: "."
    group_separator: ","
    display_token: "₾"
    token_position: "after"
    space_between: true
    payment_rows:
      - label: "Beneficiary Bank"
        value: "Example Bank; SWIFT: EXAMPLE22"
      - label: "Beneficiary"
        value: "JANE EXAMPLE"
      - label: "Account"
        value: "GE00EXAMPLE"
---
```

Rules:

- Currency codes are uppercase ASCII letters or digits, 3-8 characters, starting with a letter.
- `minor_units` is 0-4.
- Decimal and group separators must differ; the group separator may be empty.
- `display_token` may be a symbol or code. `token_position` is `before` or `after`.
- `payment_rows` contains 1-4 `label/value` mappings. Preserve legal and bank spelling exactly.

EUR preset: two minor units, `,` decimal, `.` grouping, `€` after the amount with a space.

USD preset: two minor units, `,` decimal, `.` grouping, `$` before the amount with a space.

## Client

Each `data/clients/<ALIAS>.md` contains:

```yaml
---
alias: "EC"
legal_name: "Example Company Ltd"
address_lines:
  - "1 Example Street, London, United Kingdom"
detail_lines:
  - "Company Number: 12345678"
first_invoice_number: 1
---
```

The alias is 2-3 uppercase ASCII letters. The alias and first invoice number become immutable once an invoice exists. Address lines are required; detail lines are optional.

## Ledger

`data/invoices.md` is append-only and generator-managed. Never edit invoice numbers manually. If it disagrees with `output/`, stop and repair the inconsistency before issuing another invoice.
