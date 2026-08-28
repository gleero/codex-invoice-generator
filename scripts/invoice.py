#!/usr/bin/env python3
"""Dependency-free bootstrap launcher for the Invoice Generator skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
VENV = SKILL_ROOT / ".venv"
STATE = VENV / ".invoice-runtime.json"
MIN_PYTHON = (3, 11)


def _python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _lockfile() -> Path:
    preferred = SKILL_ROOT / "requirements.lock"
    return preferred if preferred.is_file() else SKILL_ROOT / "requirements.txt"


def runtime_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in (SKILL_ROOT / "pyproject.toml", _lockfile(), Path(__file__)):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    digest.update(f"{sys.version_info.major}.{sys.version_info.minor}".encode("ascii"))
    return digest.hexdigest()


def _read_state() -> dict[str, Any] | None:
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _write_state(payload: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=STATE.parent, delete=False) as handle:
        temp = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp, STATE)
    finally:
        temp.unlink(missing_ok=True)


def ensure_runtime() -> str:
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(
            "Invoice Generator requires Python 3.11 or newer. Install it from https://www.python.org/downloads/ "
            "and run this command again."
        )
    fingerprint = runtime_fingerprint()
    state = _read_state()
    python = _python()
    if python.is_file() and state and state.get("fingerprint") == fingerprint:
        return fingerprint

    print("Preparing the private Invoice Generator environment...", file=sys.stderr)
    if not python.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    subprocess.run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(_lockfile())],
        check=True,
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-build-isolation",
            "--no-deps",
            "-e",
            str(SKILL_ROOT),
        ],
        check=True,
    )
    subprocess.run(
        [str(python), "-c", "import invoice_generator, reportlab, fitz, yaml; print(invoice_generator.__version__)"],
        check=True,
    )
    _write_state(
        {
            "fingerprint": fingerprint,
            "python": str(python),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        }
    )
    return fingerprint


def probe(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="invoice-bootstrap probe")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    marker = workspace / ".invoice-gen"
    ignored = {".DS_Store", "Thumbs.db"}
    entries = (
        [] if not workspace.exists() else sorted(item.name for item in workspace.iterdir() if item.name not in ignored)
    )
    state = "uninitialized"
    message = "Current folder is not an Invoice Generator workspace"
    if marker.exists():
        try:
            value = json.loads(marker.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("schema_version") == 1:
                state = "initialized"
                message = "Invoice Generator workspace marker is valid"
            else:
                state = "corrupt"
                message = "Workspace marker uses an unsupported schema"
        except (json.JSONDecodeError, OSError):
            state = "corrupt"
            message = "Workspace marker is corrupt"
    print(
        json.dumps(
            {
                "state": state,
                "marker_present": marker.exists(),
                "empty": not entries,
                "entries": entries[:10],
                "message": message,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "probe":
        return probe(arguments[1:])
    try:
        if arguments and arguments[0] == "bootstrap":
            ensure_runtime()
            print(_python())
            return 0
        fingerprint = ensure_runtime()
    except subprocess.CalledProcessError as exc:
        print(
            "Invoice Generator could not prepare its environment. Check internet access and permission to write "
            f"{VENV}, then try again (failed command exit code {exc.returncode}).",
            file=sys.stderr,
        )
        return 1
    environment = os.environ.copy()
    environment["INVOICE_RUNTIME_FINGERPRINT"] = fingerprint
    return subprocess.call([str(_python()), "-m", "invoice_generator", *arguments], env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
