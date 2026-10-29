#!/usr/bin/env python3
"""Audit an asset ledger and write a machine-readable rights report."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXTERNAL_TYPES = {"external", "licensed", "generated", "stock", "web"}
CLEARED = {"cleared", "used"}


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"asset ledger does not exist: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def audit(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    ledger_path = project / args.ledger
    rows = load_rows(ledger_path)
    errors: list[str] = []
    warnings: list[str] = []
    checked: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        asset_id = row.get("asset_id") or f"row-{index}"
        source_type = (row.get("source_type") or "").strip().lower()
        status = (row.get("status") or "").strip().lower()
        reference = (row.get("filename_or_url") or "").strip()
        license_value = (row.get("license") or row.get("licence") or "").strip()
        owner = (row.get("creator_or_owner") or "").strip()
        item: dict[str, Any] = {"asset_id": asset_id, "source_type": source_type, "reference": reference, "status": status}
        if not reference:
            errors.append(f"{asset_id} has no filename_or_url")
        if status not in CLEARED:
            errors.append(f"{asset_id} is not cleared or used")
        if source_type in EXTERNAL_TYPES and not license_value:
            errors.append(f"{asset_id} has no license")
        if source_type in EXTERNAL_TYPES and not owner:
            errors.append(f"{asset_id} has no creator_or_owner")
        if source_type == "generated":
            prompt = (row.get("generation_prompt") or "").strip()
            prompt_sha = (row.get("prompt_sha256") or "").strip()
            provenance = (row.get("provenance_path") or "").strip()
            if not prompt and not (len(prompt_sha) == 64 and provenance):
                errors.append(f"{asset_id} needs generation_prompt or prompt_sha256+provenance_path")
            if provenance:
                provenance_path = Path(provenance).expanduser()
                provenance_path = provenance_path.resolve() if provenance_path.is_absolute() else (project / provenance_path).resolve()
                try:
                    provenance_path.relative_to(project.resolve())
                except ValueError:
                    errors.append(f"{asset_id} provenance_path escapes project: {provenance}")
                else:
                    if (row.get("output_sha256") or "").strip() and not provenance_path.is_file():
                        errors.append(f"{asset_id} provenance_path does not exist: {provenance_path}")
        if source_type in {"original", "user-owned"} and reference and not reference.startswith(("http://", "https://")):
            local = project / reference
            if not local.is_file():
                errors.append(f"{asset_id} local file does not exist: {local}")
        if source_type == "generated":
            warnings.append(f"{asset_id} must carry generated-media disclosure in the final package")
        checked.append(item)
    report = {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "ledger": str(ledger_path),
        "asset_count": len(rows),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "assets": checked,
    }
    output = project / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit content-package rights and source provenance.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--ledger", default="03_assets/asset-ledger.csv")
    parser.add_argument("--output", default="05_publish/rights-report.json")
    parser.set_defaults(handler=audit)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
