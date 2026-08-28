#!/usr/bin/env python3
"""Validate repository-specific Codex skill metadata and invariants.

Created by Vladimir Perekladov <gleero@gmail.com>.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", re.DOTALL)


def _pinned_requirements(path: Path) -> set[str]:
    """Return normalized pinned requirement lines, excluding comments."""

    return {
        line.strip().casefold()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping with a path-specific validation error."""
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read YAML {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return value


def validate(root: Path) -> list[str]:
    """Return all locally detectable skill packaging errors."""
    errors: list[str] = []
    skill_path = root / "SKILL.md"
    try:
        skill_text = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"Cannot read SKILL.md: {exc}"]
    match = FRONTMATTER.match(skill_text)
    if not match:
        return ["SKILL.md is missing YAML frontmatter"]
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return [f"Invalid SKILL.md frontmatter: {exc}"]
    if not isinstance(frontmatter, dict):
        return ["SKILL.md frontmatter must be a mapping"]
    if frontmatter.get("name") != "invoice-generator":
        errors.append("SKILL.md name must be invoice-generator")
    description = frontmatter.get("description")
    if not isinstance(description, str) or "invoice" not in description.casefold():
        errors.append("SKILL.md description must clearly route invoice requests")

    required_phrases = (
        ".invoice-gen",
        "probe --workspace",
        "ask whether to initialize",
        "--allow-nonempty",
        "owner.md",
        "client suggest",
        "first new invoice",
        "Never include account or bank data in a web query",
    )
    for phrase in required_phrases:
        if phrase not in skill_text:
            errors.append(f"SKILL.md is missing required instruction: {phrase}")

    for relative in re.findall(r"\]\((references/[^)]+)\)", skill_text):
        if not (root / relative).is_file():
            errors.append(f"Referenced skill file is missing: {relative}")

    try:
        openai = load_yaml(root / "agents" / "openai.yaml")
        interface = openai.get("interface", {})
        if not isinstance(interface, dict):
            errors.append("agents/openai.yaml interface must be a mapping")
        elif "$invoice-generator" not in str(interface.get("default_prompt", "")):
            errors.append("default_prompt must mention $invoice-generator")
        policy = openai.get("policy", {})
        if not isinstance(policy, dict) or policy.get("allow_implicit_invocation") is not True:
            errors.append("implicit invocation must remain enabled")
    except ValueError as exc:
        errors.append(str(exc))

    stale_patterns = ("~/.codex/skills/invoice-generator", "--root <skill-root>")
    for path in (root / "SKILL.md", root / "README.md", root / "references" / "data-format.md"):
        text = path.read_text(encoding="utf-8")
        for pattern in stale_patterns:
            if pattern in text:
                errors.append(f"Stale installation or data path in {path.name}: {pattern}")

    runtime_requirements = _pinned_requirements(root / "requirements.lock")
    for name in ("requirements.txt", "requirements-dev.lock"):
        path = root / name
        requirements = _pinned_requirements(path)
        nested = sorted(item for item in requirements if item.startswith(("-r ", "--requirement ")))
        if nested:
            errors.append(f"{name} must be flat for Dependabot: {', '.join(nested)}")
        missing = sorted(runtime_requirements - requirements)
        if missing:
            errors.append(f"{name} is missing runtime pins: {', '.join(missing)}")
    return errors


def main() -> int:
    """Validate a skill root and print errors suitable for CI logs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path.cwd())
    args = parser.parse_args()
    errors = validate(args.root.expanduser().resolve())
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("Invoice Generator skill validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
