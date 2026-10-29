#!/usr/bin/env python3
"""Approve a deterministic topic/scope contract for a content package."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def contract_payload(document: dict[str, Any]) -> dict[str, Any]:
    """Return the immutable topic fields used to derive topic_sha256."""
    return {
        "content_id": document.get("content_id", ""),
        "account": document.get("account", ""),
        "canonical_topic": document.get("canonical_topic", ""),
        "in_scope": document.get("in_scope", []),
        "out_scope": document.get("out_scope", []),
        "drift_threshold": document.get("drift_threshold", 0.2),
    }


def contract_sha256(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(contract_payload(document))).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def approve(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest = load_json(project / "content.json")
    topic = args.canonical_topic.strip()
    in_scope = [item.strip() for item in args.in_scope if item.strip()]
    out_scope = [item.strip() for item in args.out_scope if item.strip()]
    if not topic or not in_scope or not args.confirm:
        raise ValueError("--canonical-topic, --in-scope and --confirm are required")
    reviewer = args.reviewer.strip()
    if manifest.get("publish_mode") == "production" and not reviewer:
        raise ValueError("production topic approval requires --reviewer")
    payload = {"content_id": manifest.get("content_id", ""), "account": manifest.get("account", ""), "canonical_topic": topic, "in_scope": in_scope, "out_scope": out_scope, "drift_threshold": float(args.drift_threshold)}
    document = {"schema_version": 1, **payload, "status": "approved", "topic_sha256": contract_sha256(payload), "approved_by": reviewer, "approved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    target = project / str((manifest.get("paths") or {}).get("topic_contract", "00_brief/topic-contract.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve a topic contract.")
    parser.add_argument("approve", choices=["approve"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--canonical-topic", required=True)
    parser.add_argument("--in-scope", nargs="+", required=True)
    parser.add_argument("--out-scope", nargs="*", default=[])
    parser.add_argument("--drift-threshold", type=float, default=0.2)
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--confirm", action="store_true")
    try:
        return approve(parser.parse_args())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
