from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from .models import ClientProfile, InvoiceError, OwnerProfile

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", re.DOTALL)
LEGAL_SUFFIXES = {
    "AG",
    "BV",
    "CO",
    "COMPANY",
    "CORP",
    "CORPORATION",
    "GMBH",
    "INC",
    "LIMITED",
    "LLC",
    "LLP",
    "LTD",
    "OOO",
    "PLC",
    "SAS",
    "SP",
    "SRL",
    "Z",
    "OO",
}
PLACEHOLDER_MARKERS = ("YOUR ", "ADD AT LEAST", "REPLACE ")


def read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InvoiceError(f"Profile file not found: {path}") from exc
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise InvoiceError(f"Missing YAML frontmatter in {path}")
    try:
        value = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise InvoiceError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InvoiceError(f"Frontmatter in {path} must be a mapping")
    return value


def load_owner(workspace: Path) -> OwnerProfile:
    return OwnerProfile.from_mapping(read_frontmatter(workspace / "data" / "owner.md"))


def validate_owner_complete(workspace: Path) -> OwnerProfile:
    owner = load_owner(workspace)
    values = [owner.role, owner.name, owner.address]
    for currency in owner.currencies.values():
        values.append(currency.display_token)
        for row in currency.payment_rows:
            values.extend((row.label, row.value))
    if any(any(marker in value.upper() for marker in PLACEHOLDER_MARKERS) for value in values):
        raise InvoiceError("Owner profile still contains template placeholders")
    return owner


def load_clients(workspace: Path) -> list[ClientProfile]:
    clients_dir = workspace / "data" / "clients"
    if not clients_dir.exists():
        raise InvoiceError(f"Client directory not found: {clients_dir}")
    clients = [ClientProfile.from_mapping(read_frontmatter(path)) for path in sorted(clients_dir.glob("*.md"))]
    aliases = [client.alias for client in clients]
    if len(aliases) != len(set(aliases)):
        raise InvoiceError("Duplicate client aliases found in data/clients")
    names = [client.legal_name.casefold() for client in clients]
    if len(names) != len(set(names)):
        raise InvoiceError("Duplicate client legal names found in data/clients")
    return clients


def find_client(workspace: Path, query: str) -> ClientProfile:
    normalized = query.strip().casefold()
    clients = load_clients(workspace)
    exact_alias = [client for client in clients if client.alias.casefold() == normalized]
    if exact_alias:
        return exact_alias[0]
    exact_name = [client for client in clients if client.legal_name.casefold() == normalized]
    if exact_name:
        return exact_name[0]
    partial = [client for client in clients if normalized in client.legal_name.casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        names = ", ".join(f"{client.alias} ({client.legal_name})" for client in partial)
        raise InvoiceError(f"Ambiguous client query. Matches: {names}")
    raise InvoiceError(f"Client not found: {query}")


def _significant_words(name: str) -> list[str]:
    camel_split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    words = re.findall(r"[A-Za-z]+", camel_split)
    significant = [word for word in words if word.upper() not in LEGAL_SUFFIXES]
    return significant or words


def generate_alias(name: str, used_aliases: Iterable[str]) -> str:
    used = {alias.upper() for alias in used_aliases}
    words = _significant_words(name)
    if not words:
        raise InvoiceError("Cannot generate an alias from a name without Latin letters")

    candidates: list[str] = []
    if len(words) >= 2:
        candidates.extend(
            [
                "".join(word[0] for word in words[:2]),
                "".join(word[0] for word in words[:3]),
                words[0][0] + words[-1][:2],
            ]
        )
    else:
        compact = words[0]
        candidates.extend([compact[:2], compact[:3]])

    compact_all = "".join(words).upper()
    for second_index in range(1, len(compact_all)):
        candidates.append(compact_all[0] + compact_all[second_index])
        if second_index + 1 < len(compact_all):
            candidates.append(compact_all[0] + compact_all[second_index : second_index + 2])

    for candidate in candidates:
        alias = re.sub(r"[^A-Z]", "", candidate.upper())[:3]
        if 2 <= len(alias) <= 3 and alias not in used:
            return alias
    raise InvoiceError("Could not generate a unique 2-3 letter alias; provide --alias")


def suggest_alias(workspace: Path, legal_name: str) -> str:
    return generate_alias(legal_name, (client.alias for client in load_clients(workspace)))


def add_client(
    workspace: Path,
    *,
    legal_name: str,
    address_lines: list[str],
    detail_lines: list[str],
    alias: str,
    first_invoice_number: int,
) -> ClientProfile:
    existing = load_clients(workspace)
    client = ClientProfile.from_mapping(
        {
            "alias": alias,
            "legal_name": legal_name,
            "address_lines": address_lines,
            "detail_lines": detail_lines,
            "first_invoice_number": first_invoice_number,
        }
    )
    if any(item.alias == client.alias for item in existing):
        raise InvoiceError(f"Alias already exists: {client.alias}")
    if any(item.legal_name.casefold() == client.legal_name.casefold() for item in existing):
        raise InvoiceError(f"Client already exists: {client.legal_name}")
    path = workspace / "data" / "clients" / f"{client.alias}.md"
    if path.exists():
        raise InvoiceError(f"Refusing to overwrite client profile: {path}")
    data = {
        "alias": client.alias,
        "legal_name": client.legal_name,
        "address_lines": list(client.address_lines),
        "detail_lines": list(client.detail_lines),
        "first_invoice_number": client.first_invoice_number,
    }
    frontmatter = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120).strip()
    path.write_text(
        f"---\n{frontmatter}\n---\n\n# {client.legal_name}\n\nPrivate client profile managed by Invoice Generator.\n",
        encoding="utf-8",
    )
    return client
