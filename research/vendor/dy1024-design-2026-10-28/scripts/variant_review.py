#!/usr/bin/env python3
"""Review platform variants one by one before the quality gate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_project(project: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    manifest_path = project / "content.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    variants_path = project / str(manifest.get("paths", {}).get("variants", "05_publish/variants.json"))
    variants = json.loads(variants_path.read_text(encoding="utf-8"))
    if not isinstance(variants, dict):
        raise SystemExit("variants manifest must be a JSON object")
    return manifest, variants_path, variants


def validate(variants: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if variants.get("planning_draft") is True or variants.get("production_eligible") is False:
        errors.append("planning-draft variants are not eligible for approval")
    platforms = variants.get("platforms", {})
    if not isinstance(platforms, dict) or not platforms:
        return ["platforms must contain at least one platform"]
    if set(platforms) != {"douyin"}:
        errors.append("only douyin variants are in scope")
    for platform, items in platforms.items():
        if not isinstance(items, list) or not items:
            errors.append(f"platform {platform} has no variants")
            continue
        for item in items:
            if not isinstance(item, dict):
                errors.append(f"variant entry is not an object: {platform}")
                continue
            variant_id = str(item.get("variant_id", platform))
            if item.get("status") != "approved":
                errors.append(f"variant is not approved: {variant_id}")
            if not str(item.get("reviewer", "")).strip():
                errors.append(f"variant reviewer is missing: {variant_id}")
            if not str(item.get("reviewed_at", "")).strip():
                errors.append(f"variant reviewed_at is missing: {variant_id}")
            if platform == "douyin" and item.get("safe_area_checked") is not True:
                errors.append(f"douyin safe-area confirmation is missing: {variant_id}")
    if variants.get("status") != "approved":
        errors.append("top-level variant status must be approved")
    return errors


def refresh_status(variants: dict[str, Any]) -> None:
    items = [item for values in variants.get("platforms", {}).values() if isinstance(values, list) for item in values if isinstance(item, dict)]
    if not items:
        variants["status"] = "pending"
    elif any(item.get("status") == "blocked" for item in items):
        variants["status"] = "blocked"
    elif all(item.get("status") == "approved" for item in items):
        variants["status"] = "approved"
    elif any(item.get("status") in {"pending", "review-required"} for item in items):
        variants["status"] = "review-required"
    else:
        variants["status"] = "ready"


def check(args: argparse.Namespace) -> int:
    _, _, variants = load_project(Path(args.project).expanduser().resolve())
    errors = validate(variants)
    result = {"passed": not errors, "status": variants.get("status"), "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] or not args.strict else 1


def approve(args: argparse.Namespace) -> int:
    if not args.confirm:
        raise SystemExit("Variant approval is a human action. Re-run with --confirm after review.")
    if not args.reviewer.strip():
        raise SystemExit("--reviewer is required")
    manifest, path, variants = load_project(Path(args.project).expanduser().resolve())
    if variants.get("planning_draft") is True or variants.get("production_eligible") is False:
        raise SystemExit("planning draft variants must not be approved; complete copy strategy first")
    found = None
    found_platform = ""
    for platform, items in variants.get("platforms", {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and str(item.get("variant_id", "")) == args.variant_id:
                found = item
                found_platform = str(platform)
                break
    if found is None:
        raise SystemExit(f"unknown variant_id: {args.variant_id}")
    if found.get("status") == "blocked":
        raise SystemExit("blocked variants must be revised before approval")
    platform = args.platform.strip() or found_platform
    if args.platform.strip() and args.platform.strip() != found_platform:
        raise SystemExit(f"platform does not match variant: expected {found_platform}")
    if platform == "douyin" and not args.safe_area_checked:
        raise SystemExit("Douyin approval requires --safe-area-checked")
    found["status"] = "approved"
    found["reviewer"] = args.reviewer.strip()
    found["reviewed_at"] = now()
    found["review_note"] = args.note.strip()
    if args.safe_area_checked:
        found["safe_area_checked"] = True
    refresh_status(variants)
    path.write_text(json.dumps(variants, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"content_id": manifest.get("content_id", ""), "variant_id": args.variant_id, "status": variants["status"]}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review platform variants one by one.")
    child = parser.add_subparsers(dest="command", required=True)
    check_parser = child.add_parser("check")
    check_parser.add_argument("--project", required=True)
    check_parser.add_argument("--strict", action="store_true")
    check_parser.set_defaults(handler=check)
    approve_parser = child.add_parser("approve")
    approve_parser.add_argument("--project", required=True)
    approve_parser.add_argument("--variant-id", required=True)
    approve_parser.add_argument("--platform", default="")
    approve_parser.add_argument("--reviewer", required=True)
    approve_parser.add_argument("--note", default="")
    approve_parser.add_argument("--safe-area-checked", action="store_true")
    approve_parser.add_argument("--confirm", action="store_true")
    approve_parser.set_defaults(handler=approve)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
