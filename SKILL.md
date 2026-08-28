---
name: invoice-generator
description: Create and track outgoing client invoices in a workspace-local Markdown database. Use when the user asks to issue, prepare, generate, or number an invoice, add an invoice client, or configure invoice payment details. Do not use for extracting supplier invoices or accounting reconciliation.
metadata:
  short-description: Generate and track client invoices
---

# Invoice Generator

Keep code and runtime inside this skill. Keep private profiles, the ledger, and generated PDFs inside the user's current workspace. Never invent legal or banking details.

Resolve `SKILL_ROOT` as the directory containing this file and `WORKSPACE` as the current folder opened in Codex. Run all deterministic operations through:

```text
python3 <SKILL_ROOT>/scripts/invoice.py ...
```

Use `py -3` instead of `python3` on Windows.

## Workspace gate

Before handling any invoice request, run the dependency-free probe:

```text
python3 <SKILL_ROOT>/scripts/invoice.py probe --workspace <WORKSPACE>
```

- If `.invoice-gen` is absent, ask whether to initialize this exact folder. Do not bootstrap or write anything before the answer.
- If the folder is non-empty, name the reported entries and warn that invoice data and output will be added alongside them.
- After explicit approval, run the launcher with `--workspace <WORKSPACE> workspace init --confirmed --json`. Add `--allow-nonempty` only when the user approved a non-empty folder.
- The launcher may need approval to create `<SKILL_ROOT>/.venv` and download pinned packages. The workspace must never receive code or a virtual environment.
- If the marker is corrupt, explain the problem and ask before running `workspace repair --confirmed`. Never replace it silently.
- If the marker exists, run `workspace status --json`. Trust the marker as a cache only; Markdown remains authoritative.

## Owner onboarding

When owner status is not `ready`, finish `data/owner.md` in this order:

1. Ask which currencies the owner accepts and collect the payment details for at least one currency.
2. Ask for legal status, legal name, business address, and IANA timezone.
3. Preserve bank and legal values exactly as supplied. Run `owner validate --json` after editing.

EUR and USD use the documented presets. For another currency, research only its code, minor units, symbol, and customary display using SIX ISO 4217 and Unicode CLDR. Never include account or bank data in a web query. If code-versus-symbol or placement is ambiguous, show concrete alternatives and ask the user to choose. If research is unavailable, ask directly. Read [references/data-format.md](references/data-format.md) when writing or repairing profiles.

## Client and invoice workflow

1. Find the client by alias or legal name. For a new client, require the official legal name and at least one address line; identifiers and contacts are optional.
2. Run `client suggest --name <LEGAL_NAME> --json`. Tell the user the suggested 2-3 letter alias and explicitly ask whether it is acceptable.
3. Ask whether the first new invoice should be `001`; if not, ask for the first positive number. Only after both answers run `client add` with the confirmed `--alias` and `--first-number`.
4. Collect only missing amount, currency, and activity. Infer the currency from an explicit code or unambiguous symbol. If it is not configured in `owner.md`, configure it first. Use today's date in the owner's timezone. Include a period only when supplied.
5. Normalize the activity into concise professional English while preserving official names and identifiers.
6. Once required data is present, issue without another confirmation:

```text
python3 <SKILL_ROOT>/scripts/invoice.py --workspace <WORKSPACE> issue \
  --client <ALIAS_OR_NAME> --amount <DECIMAL> --currency <CODE> \
  --description <ENGLISH_DESCRIPTION> [--period <TEXT>] [--date <YYYY-MM-DD>] --json
```

Return the absolute clickable PDF path from the command. Do not manually edit the ledger, consume a number after failure, rename a generated PDF, or overwrite an existing output.

## Invariants

- Numbering is independent per confirmed client alias and begins at its saved `first_invoice_number`.
- Output is `output/<safe company name>/<ALIAS>-<NNN>.pdf`, with at least three digits.
- EUR renders as `1.500,00 €`; USD renders as `$ 1.500,00`.
- Payment details contain one to four labeled rows. Stop with an actionable error if any content cannot fit on one A4 page.
- A successful PDF is validated before the ledger is appended. A failure must leave both ledger and final output unchanged.
