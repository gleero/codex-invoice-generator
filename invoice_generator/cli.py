from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__
from .models import InvoiceError, InvoiceRequest
from .profiles import add_client, find_client, load_clients, suggest_alias, validate_owner_complete
from .service import default_issue_date, issue_invoice, validate_repository
from .workspace import (
    initialize_workspace,
    probe_as_dict,
    probe_workspace,
    refresh_marker,
    repair_workspace,
    workspace_status,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="invoice", description="Generate and track client invoices")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="workspace containing data/ and output/")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    workspace_parser = subparsers.add_parser("workspace", help="inspect or initialize a workspace")
    workspace_subparsers = workspace_parser.add_subparsers(dest="workspace_command", required=True)
    for command in ("probe", "status"):
        item = workspace_subparsers.add_parser(command)
        item.add_argument("--json", action="store_true")
    init_parser = workspace_subparsers.add_parser("init")
    init_parser.add_argument("--confirmed", action="store_true")
    init_parser.add_argument("--allow-nonempty", action="store_true")
    init_parser.add_argument("--json", action="store_true")
    repair_parser = workspace_subparsers.add_parser("repair")
    repair_parser.add_argument("--confirmed", action="store_true")
    repair_parser.add_argument("--json", action="store_true")

    owner_parser = subparsers.add_parser("owner", help="validate the owner profile")
    owner_subparsers = owner_parser.add_subparsers(dest="owner_command", required=True)
    owner_validate = owner_subparsers.add_parser("validate")
    owner_validate.add_argument("--json", action="store_true")

    client_parser = subparsers.add_parser("client", help="manage client profiles")
    client_subparsers = client_parser.add_subparsers(dest="client_command", required=True)
    list_parser = client_subparsers.add_parser("list", help="list known clients")
    list_parser.add_argument("--json", action="store_true")
    suggest_parser = client_subparsers.add_parser("suggest", help="suggest an unused alias without writing")
    suggest_parser.add_argument("--name", required=True, help="official legal name")
    suggest_parser.add_argument("--json", action="store_true")
    add_parser = client_subparsers.add_parser("add", help="add a confirmed normalized client profile")
    add_parser.add_argument("--name", required=True, help="official legal name")
    add_parser.add_argument("--address", action="append", required=True, help="address line; repeat as needed")
    add_parser.add_argument("--detail", action="append", default=[], help="registration/contact line; repeat as needed")
    add_parser.add_argument("--alias", required=True, help="confirmed fixed 2-3 letter alias")
    add_parser.add_argument("--first-number", required=True, type=int, help="confirmed first invoice number")
    add_parser.add_argument("--json", action="store_true")

    validate_parser = subparsers.add_parser("validate", help="validate owner, clients, and ledger")
    validate_parser.add_argument("--json", action="store_true")

    issue_parser = subparsers.add_parser("issue", help="issue the next invoice for a client")
    issue_parser.add_argument("--client", required=True, help="client alias or legal name")
    issue_parser.add_argument("--amount", required=True, help="positive decimal amount without grouping separators")
    issue_parser.add_argument("--currency", required=True, help="configured 3-8 character currency code")
    issue_parser.add_argument("--description", required=True, help="professional English activity description")
    issue_parser.add_argument("--period", help="optional service period text")
    issue_parser.add_argument("--date", dest="issue_date", type=date.fromisoformat, help="YYYY-MM-DD")
    issue_parser.add_argument("--json", action="store_true")
    return parser


def _print(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    elif isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _require_workspace(workspace: Path) -> None:
    workspace_status(workspace)


def run(args: argparse.Namespace) -> int:
    workspace = args.workspace.expanduser().resolve()
    if args.command == "workspace":
        if args.workspace_command == "probe":
            probe = probe_as_dict(probe_workspace(workspace))
            _print(probe, as_json=args.json)
            return 0
        if args.workspace_command == "init":
            marker = initialize_workspace(
                workspace,
                confirmed=args.confirmed,
                allow_nonempty=args.allow_nonempty,
            )
            _print(marker, as_json=args.json)
            return 0
        if args.workspace_command == "repair":
            marker = repair_workspace(workspace, confirmed=args.confirmed)
            _print(marker, as_json=args.json)
            return 0
        marker = workspace_status(workspace)
        _print(marker, as_json=args.json)
        return 0

    _require_workspace(workspace)
    if args.command == "owner":
        owner = validate_owner_complete(workspace)
        marker = refresh_marker(workspace)
        result = {"status": "ready", "name": owner.name, "currencies": sorted(owner.currencies), "marker": marker}
        _print(result, as_json=args.json)
        return 0

    if args.command == "validate":
        client_count, invoice_count = validate_repository(workspace)
        marker = refresh_marker(workspace)
        result = {"status": "ok", "clients": client_count, "invoices": invoice_count, "marker": marker}
        _print(result, as_json=args.json)
        return 0

    if args.command == "client":
        if args.client_command == "list":
            clients = [
                {
                    "alias": client.alias,
                    "legal_name": client.legal_name,
                    "first_invoice_number": client.first_invoice_number,
                }
                for client in load_clients(workspace)
            ]
            if args.json:
                _print(clients, as_json=True)
            else:
                for client in clients:
                    print(f"{client['alias']}\t{client['legal_name']}\tfirst={client['first_invoice_number']}")
            return 0
        if args.client_command == "suggest":
            alias = suggest_alias(workspace, args.name)
            _print({"alias": alias, "legal_name": args.name}, as_json=args.json)
            return 0
        client = add_client(
            workspace,
            legal_name=args.name,
            address_lines=args.address,
            detail_lines=args.detail,
            alias=args.alias,
            first_invoice_number=args.first_number,
        )
        refresh_marker(workspace)
        _print(
            {
                "alias": client.alias,
                "legal_name": client.legal_name,
                "first_invoice_number": client.first_invoice_number,
            },
            as_json=args.json,
        )
        return 0

    if args.command == "issue":
        client = find_client(workspace, args.client)
        request = InvoiceRequest.create(
            client=client,
            amount=args.amount,
            currency=args.currency,
            description=args.description,
            issue_date=args.issue_date or default_issue_date(workspace),
            period=args.period,
        )
        path = issue_invoice(workspace, request)
        _print({"status": "issued", "pdf": str(path)}, as_json=args.json)
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        return run(parser.parse_args(argv))
    except InvoiceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
