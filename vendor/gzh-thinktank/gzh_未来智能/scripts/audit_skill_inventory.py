#!/usr/bin/env python3
"""Create a parameterized, secret-free inventory of local SKILL.md files."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:100]:
        if line.strip() == "---":
            break
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if match:
            result[match.group(1)] = match.group(2).strip().strip("'\"")
    return result


def scan(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("SKILL.md")):
        rel = path.relative_to(root).as_posix()
        if any(part in {".git", "node_modules", ".venv", "__pycache__"} for part in path.parts):
            continue
        if rel.startswith("skills/_archive/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        meta = _frontmatter(text)
        rows.append({
            "path": rel,
            "name": meta.get("name", ""),
            "display_name": meta.get("display_name", ""),
            "version": meta.get("version", ""),
            "sha256": _sha256(path),
            "lines": len(text.splitlines()),
        })
    return {
        "schema_version": 1,
        "contract": "skill-inventory-v1",
        "root": str(root),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "skill_count": len(rows),
        "skills": rows,
    }


def as_markdown(doc: dict[str, Any]) -> str:
    lines = [
        "# Skill inventory",
        "",
        f"> contract: `{doc['contract']}`; count: {doc['skill_count']}; scanned_at: {doc['scanned_at']}",
        "",
        "| Path | Name | Version | SHA-256 | Lines |",
        "|---|---|---|---|---:|",
    ]
    for row in doc["skills"]:
        lines.append(f"| `{row['path']}` | {row['name']} | {row['version']} | `{row['sha256']}` | {row['lines']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    root = args.root.expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    if not root.is_dir():
        print(f"SKILL INVENTORY BLOCKED: root not found: {root}")
        return 1
    doc = scan(root)
    content = json.dumps(doc, ensure_ascii=False, indent=2) + "\n" if args.format == "json" else as_markdown(doc)
    if args.output:
        output = args.output.expanduser()
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(f"SKILL INVENTORY WRITTEN: {output.resolve()} ({doc['skill_count']} skills)")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
