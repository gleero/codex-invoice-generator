# Invoice Generator for Codex

[![CI](https://github.com/gleero/codex-invoice-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/gleero/codex-invoice-generator/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A portable Codex skill that generates deterministic, single-page PDF invoices, keeps client details in Markdown,
and maintains an independent invoice sequence for each company.

The installed skill and your private invoice workspace stay separate:

```text
~/.agents/skills/invoice-generator/   <- skill code, fonts, and private .venv
~/Documents/My Invoices/              <- your details, clients, ledger, and PDFs
```

No Python source code, dependencies, or virtual environment is copied into your invoice workspace.

## Requirements

- macOS, Linux, or Windows;
- [Python 3.11 or newer](https://www.python.org/downloads/);
- Codex desktop, Codex CLI, or the Codex IDE extension;
- Git and access to this [GitHub repository](https://github.com/gleero/codex-invoice-generator).

Python is the only runtime prerequisite. The skill creates and maintains its own virtual environment on first use.

## Install on macOS or Linux

Open Terminal and run:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/gleero/codex-invoice-generator.git "$HOME/.agents/skills/invoice-generator"
```

Fully restart Codex. Personal skills in `$HOME/.agents/skills` are officially supported; if Codex does not detect a
new skill immediately, restart the application. See the [Codex Skills documentation](https://developers.openai.com/codex/skills).

## Install on Windows PowerShell

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/gleero/codex-invoice-generator.git "$HOME\.agents\skills\invoice-generator"
```

Fully restart Codex after cloning.

## Create your invoice workspace

1. Create a normal folder, for example `Documents/My Invoices`.
2. Open that exact folder as your workspace in Codex.
3. Do not install packages or run setup commands manually.
4. Ask Codex for an invoice immediately, for example:

   > Issue an invoice to Example Ltd for EUR 1,500 for website development.

If the folder has not been configured, Codex will ask something similar to:

> This folder is not an Invoice Generator workspace yet. Initialize it here?

Codex always asks before initialization. If the folder is not empty, it also shows several existing items and warns
you before writing anything. Until you approve, the skill neither creates workspace files nor installs dependencies.

After approval, Codex:

1. creates a private `.venv` inside the installed skill;
2. creates `.invoice-gen`, `data/`, and `output/` in your workspace;
3. asks for your accepted currencies and payment instructions;
4. asks for your legal name, business status, address, and timezone;
5. resumes the original invoice request.

Codex may request permission once to download Python packages and write the skill's private environment.

## Complete first-run example

You do not type any of the commands shown in this dialogue. A typical first run looks like this:

> **You:** Issue an invoice to Example Company Ltd for EUR 1,500 for website development.
>
> **Codex:** This folder is not an Invoice Generator workspace yet. Initialize it here? The folder is not empty:
> `notes.md` already exists. I will add only `.invoice-gen`, `.gitignore`, `data/`, and `output/`.
>
> **You:** Yes.
>
> **Codex:** Which currencies do you accept? For each currency, send the payment lines exactly as they should appear
> in the PDF. At least one currency is required.
>
> **You:** EUR. Beneficiary Bank: Example Bank; Beneficiary: JANE EXAMPLE; Account: XX00EXAMPLE.
>
> **Codex:** Now I need your legal status, name, business address, and timezone, for example `Asia/Tbilisi`.
>
> **You:** Individual Entrepreneur, Jane Example, 1 Example Street, Tbilisi, Georgia, Asia/Tbilisi.
>
> **Codex:** The client's official address is still missing.
>
> **You:** 10 Sample Road, London, United Kingdom. Company Number: 00000001.
>
> **Codex:** I suggest the permanent alias `EC`. Does that work?
>
> **You:** Yes.
>
> **Codex:** Should the first new invoice be `001`? If not, what should the starting number be?
>
> **You:** Yes, start at `001`.
>
> **Codex:** Done: [EC-001.pdf](output/Example%20Company%20Ltd/EC-001.pdf).

On later requests, Codex reads `.invoice-gen`, revalidates only the Markdown files whose fingerprints changed, and
continues issuing invoices. You do not repeat setup.

## Adding the first client

For every new company, Codex:

1. normalizes the supplied details without inventing missing information;
2. proposes an unused two- or three-letter alias, such as `EC`;
3. asks you to approve that alias;
4. asks whether numbering should start at `001`, or at another number;
5. saves the client only after receiving both answers.

After the first invoice, the alias and starting number are treated as permanent. Each client has an independent
sequence.

## Workspace contents

```text
My Invoices/
|-- .invoice-gen          state cache without bank or client details
|-- .gitignore            protects private files from accidental commits
|-- data/
|   |-- owner.md          your identity, currencies, and payment instructions
|   |-- clients/          one Markdown profile per client
|   `-- invoices.md       issued-invoice ledger
`-- output/
    `-- Example Ltd/
        `-- EC-001.pdf
```

Updating or uninstalling the skill does not delete this workspace. Never publish `data/` or `output/` in a public
Git repository.

## Everyday requests

```text
Issue a USD 2,000 invoice to WG for software development in August.

Add a new client. Here are the details: ...

Check my client database and invoice numbering.

Add GEL as a payment currency and show the ₾ symbol after the amount.
```

If the amount, currency, or activity is missing, Codex asks only for the missing information. Once all required data
is available, it generates the PDF without an extra confirmation step.

## Update the skill

```bash
git -C "$HOME/.agents/skills/invoice-generator" pull
```

On the next request, the launcher detects dependency changes and updates its private `.venv` when needed. Your
workspace remains untouched.

## Uninstall the skill

Delete only `~/.agents/skills/invoice-generator`, then restart Codex. Your separate workspace, Markdown data, and PDFs
remain in place.

## Troubleshooting

### Codex cannot find the skill

Confirm that this file exists:

```text
~/.agents/skills/invoice-generator/SKILL.md
```

Then fully restart Codex.

### Codex reports a Python error

Install Python 3.11+ from [python.org](https://www.python.org/downloads/), close Codex, and open it again.

### You opened the wrong folder

Do not approve initialization. Open the intended invoice folder in Codex and repeat the original request.

### `.invoice-gen` is corrupt

Ask Codex: `Repair the Invoice Generator marker in this folder.` The skill asks for confirmation, backs up the damaged
marker, and rebuilds the cache from the Markdown source of truth.

### An invoice does not fit on one page

The generator never clips overflowing content. It reports the field that is too long; shorten that field and retry.

## Advanced CLI usage

Commands use the current directory as the workspace unless `--workspace` is provided:

```bash
python3 ~/.agents/skills/invoice-generator/scripts/invoice.py probe --workspace "$PWD"

python3 ~/.agents/skills/invoice-generator/scripts/invoice.py \
  --workspace "$PWD" workspace status --json

python3 ~/.agents/skills/invoice-generator/scripts/invoice.py \
  --workspace "$PWD" issue --client EC --amount 1500 --currency EUR \
  --description "Software development services"
```

The dependency-free `probe` command never creates an environment or writes workspace files.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pyright
.venv/bin/pytest --cov=invoice_generator --cov-branch --cov-fail-under=90
.venv/bin/python scripts/validate_skill.py .
npm ci
npm run lint:md
```

Use `scripts/compare_references.py` for local reference-PDF comparisons. Reference PDFs contain private data and are
intentionally excluded from Git.

### Versioning and releases

The version is stored in `pyproject.toml` and synchronized with the Python and npm metadata:

```bash
.venv/bin/bump-my-version show current_version
.venv/bin/bump-my-version bump patch
.venv/bin/bump-my-version bump minor
.venv/bin/bump-my-version bump major
```

Version commands update files but intentionally do not create commits or Git tags. Review the diff, run the complete
test suite, create a release commit, and then create an annotated `vX.Y.Z` tag.

## Privacy and security

Owner details, client profiles, source PDFs, and generated invoices are excluded from this repository. The skill does
not send banking details to web searches. Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Author

Created and maintained by **Vladimir Perekladov** ([gleero@gmail.com](mailto:gleero@gmail.com)).

## License

Source code is available under the [MIT License](LICENSE). Bundled fonts retain their own copyright notices and SIL
Open Font License terms in `assets/fonts/`.
