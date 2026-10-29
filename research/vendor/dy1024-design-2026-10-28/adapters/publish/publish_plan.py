#!/usr/bin/env python3
"""Build a credential-free publishing plan for manual or official posting."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FORBIDDEN = ("cookie", "token", "password", "secret", "access_key", "authorization")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def has_credentials(value: Any, path: str = "") -> bool:
    if isinstance(value, dict):
        return any(any(marker in str(key).lower() for marker in FORBIDDEN) or has_credentials(item, f"{path}.{key}") for key, item in value.items())
    if isinstance(value, list):
        return any(has_credentials(item, f"{path}[]") for item in value)
    return False


def run(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {}
    if args.input:
        input_path = Path(args.input).expanduser().resolve()
        try:
            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise SystemExit(f"invalid publish-plan input: {error}") from error
        if not isinstance(payload, dict):
            raise SystemExit("publish-plan input must be a JSON object")
    if has_credentials(payload):
        raise SystemExit("publish plan refuses credentials, cookies or access tokens; use a secure manual/official API adapter outside this package")
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    hashtags = args.hashtags.split(",") if args.hashtags else payload.get("hashtags", [])
    if isinstance(hashtags, str):
        hashtags = [hashtags]
    report = {
        "schema_version": 1,
        "planned_at": now(),
        "status": "approved" if args.approve else "ready",
        "passed": True,
        "platform": args.platform or payload.get("platform", "douyin"),
        "method": args.method or payload.get("method", "manual-or-official"),
        "title": args.title or payload.get("title", ""),
        "hashtags": [str(item).strip() for item in hashtags if str(item).strip()],
        "cover": args.cover or payload.get("cover", ""),
        "audience": payload.get("audience", ""),
        "scheduled_at": payload.get("scheduled_at", ""),
        "receipt_required": True,
        "credential_policy": "No cookies, tokens or passwords stored in the content package.",
        "notes": payload.get("notes", "After posting, record media_id/url and published_at in publish-receipt.json."),
    }
    errors = []
    if report["platform"] != "douyin":
        errors.append("unsupported platform: only douyin is in scope")
    if report["method"] not in {"manual", "manual-or-official", "official-api", "draft"}:
        errors.append("unsupported publish method")
    if not report["title"]:
        errors.append("title is required")
    report["errors"] = errors
    report["passed"] = not errors
    if errors:
        report["status"] = "blocked"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a credential-free platform publishing plan.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--input")
    parser.add_argument("--platform")
    parser.add_argument("--method", choices=["manual", "manual-or-official", "official-api", "draft"])
    parser.add_argument("--title")
    parser.add_argument("--hashtags")
    parser.add_argument("--cover")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.set_defaults(handler=run)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))

