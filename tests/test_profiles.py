from __future__ import annotations

from pathlib import Path

import pytest

from invoice_generator.models import InvoiceError
from invoice_generator.profiles import (
    add_client,
    find_client,
    generate_alias,
    read_frontmatter,
    suggest_alias,
    validate_owner_complete,
)


def test_alias_generation_matches_reference_names() -> None:
    assert generate_alias("Widget Group Ltd", []) == "WG"
    assert generate_alias("Acme Example Ltd", []) == "AE"


def test_alias_collision_uses_another_unique_candidate() -> None:
    assert generate_alias("Anna Eshwood Ltd", ["AE"]) != "AE"


def test_suggest_does_not_write_and_add_requires_confirmed_values(workspace_root: Path) -> None:
    before = set((workspace_root / "data" / "clients").iterdir())
    assert suggest_alias(workspace_root, "Northwind Trading Ltd") == "NT"
    assert set((workspace_root / "data" / "clients").iterdir()) == before
    client = add_client(
        workspace_root,
        legal_name="Northwind Trading Ltd",
        address_lines=["1 Harbour Road, London, United Kingdom"],
        detail_lines=["Company Number: 12345678"],
        alias="NT",
        first_invoice_number=42,
    )
    assert client.first_invoice_number == 42
    assert find_client(workspace_root, "northwind") == client
    assert read_frontmatter(workspace_root / "data" / "clients" / "NT.md")["first_invoice_number"] == 42


def test_duplicate_alias_and_name_are_rejected(workspace_root: Path) -> None:
    with pytest.raises(InvoiceError, match="Alias already exists"):
        add_client(
            workspace_root,
            legal_name="Another Enterprise",
            address_lines=["1 Road"],
            detail_lines=[],
            alias="AE",
            first_invoice_number=1,
        )
    with pytest.raises(InvoiceError, match="Client already exists"):
        add_client(
            workspace_root,
            legal_name="Acme Example Ltd",
            address_lines=["1 Road"],
            detail_lines=[],
            alias="AX",
            first_invoice_number=1,
        )


def test_corrupt_markdown_and_incomplete_owner_are_rejected(tmp_path: Path, workspace_root: Path) -> None:
    path = tmp_path / "broken.md"
    path.write_text("# no frontmatter\n", encoding="utf-8")
    with pytest.raises(InvoiceError, match="Missing YAML frontmatter"):
        read_frontmatter(path)
    owner_path = workspace_root / "data" / "owner.md"
    owner_path.write_text(owner_path.read_text(encoding="utf-8").replace("Test Owner", "YOUR NAME"), encoding="utf-8")
    with pytest.raises(InvoiceError, match="placeholders"):
        validate_owner_complete(workspace_root)


def test_invalid_alias_source_and_ambiguous_lookup(workspace_root: Path) -> None:
    with pytest.raises(InvoiceError, match="without Latin"):
        generate_alias("東京", [])
    add_client(
        workspace_root,
        legal_name="Acme Europe Ltd",
        address_lines=["1 Road"],
        detail_lines=[],
        alias="AU",
        first_invoice_number=1,
    )
    with pytest.raises(InvoiceError, match="Ambiguous"):
        find_client(workspace_root, "Acme")
    with pytest.raises(InvoiceError, match="not found"):
        find_client(workspace_root, "Missing")
