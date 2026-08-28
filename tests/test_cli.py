from __future__ import annotations

import json
from pathlib import Path

from invoice_generator.cli import main


def invoke(workspace: Path, *arguments: str) -> int:
    return main(["--workspace", str(workspace), *arguments])


def test_workspace_cli_lifecycle(tmp_path: Path, capsys: object) -> None:
    workspace = tmp_path / "workspace"
    assert invoke(workspace, "workspace", "probe", "--json") == 0
    assert invoke(workspace, "workspace", "init", "--json") == 2
    assert invoke(workspace, "workspace", "init", "--confirmed", "--json") == 0
    assert invoke(workspace, "workspace", "status", "--json") == 0
    assert invoke(workspace, "owner", "validate", "--json") == 2


def test_client_and_invoice_cli(workspace_root: Path, capsys: object) -> None:
    assert invoke(workspace_root, "owner", "validate", "--json") == 0
    assert invoke(workspace_root, "client", "list", "--json") == 0
    assert invoke(workspace_root, "client", "suggest", "--name", "Northwind Trading Ltd", "--json") == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert '"alias": "NT"' in captured.out

    assert (
        invoke(
            workspace_root,
            "client",
            "add",
            "--name",
            "Northwind Trading Ltd",
            "--address",
            "1 Harbour Road, London",
            "--detail",
            "Company Number: 123",
            "--alias",
            "NT",
            "--first-number",
            "12",
            "--json",
        )
        == 0
    )
    assert invoke(workspace_root, "validate", "--json") == 0
    assert (
        invoke(
            workspace_root,
            "issue",
            "--client",
            "NT",
            "--amount",
            "1500",
            "--currency",
            "EUR",
            "--description",
            "Software development services",
            "--period",
            "August 2026",
            "--date",
            "2026-08-28",
            "--json",
        )
        == 0
    )
    output = capsys.readouterr()  # type: ignore[attr-defined]
    last = json.loads(output.out.strip().splitlines()[-1])
    assert last["status"] == "issued"
    assert Path(last["pdf"]).name == "NT-012.pdf"


def test_repair_cli(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    assert invoke(workspace, "workspace", "init", "--confirmed") == 0
    (workspace / ".invoice-gen").write_text("broken", encoding="utf-8")
    assert invoke(workspace, "workspace", "repair") == 2
    assert invoke(workspace, "workspace", "repair", "--confirmed", "--json") == 0
