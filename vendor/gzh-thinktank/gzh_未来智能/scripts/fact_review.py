#!/usr/bin/env python3
"""Prepare and validate an independent semantic fact-review receipt.

``verify_claims.py`` proves provenance only.  This module creates a human
review packet and validates the receipt needed for benchmark/paper-fact or
high-risk claims.  It intentionally cannot decide truth itself; an empty or
agent-authored receipt remains blocked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from workspace_paths import resolve_article_workspace  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "fact-review-v1"
REQUIRED_VERDICTS = {"supported", "qualified", "rejected"}
STRICT_CLAIM_TYPES = {"benchmark", "paper-fact", "paper_fact", "medical", "legal", "financial"}


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _claims_digest(claims: list[dict[str, Any]]) -> str:
    body = json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prepare(article: Path) -> int:
    source_path = article / "sources.json"
    source_doc = _json(source_path)
    claims = source_doc.get("claims") if isinstance(source_doc, dict) else None
    if not source_path.is_file() or not isinstance(claims, list) or not claims:
        print("FACT REVIEW BLOCKED: sources.json 缺少 claims")
        return 1
    records = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        records.append({
            "claim_id": str(claim.get("id") or ""),
            "statement": str(claim.get("statement") or ""),
            "claim_type": str(claim.get("claim_type") or ""),
            "source_ids": claim.get("source_ids", []),
            "evidence_locator": claim.get("evidence_locator", []),
            "verdict": "pending",
            "evidence_excerpt": "",
            "scope_checked": False,
            "counterevidence_checked": False,
            "wording_change": "",
            "reviewer_note": "",
        })
    output = {
        "schema_version": 1,
        "contract": CONTRACT,
        "status": "pending_human",
        "reviewer_type": "human",
        "reviewer": "",
        "signed_by": "",
        "approval_event_id": "",
        "prepared_at": _now(),
        "reviewed_at": "",
        "sources_digest": _sha256(source_path),
        "claims_digest": _claims_digest([item for item in claims if isinstance(item, dict)]),
        "semantic_truth_check": "pending_independent_human_review",
        "claims": records,
    }
    (article / "fact-review.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"FACT REVIEW PACKET CREATED: {len(records)} claims; status=pending_human")
    return 0


def validate(article: Path, require: bool = True) -> list[str]:
    path = article / "fact-review.json"
    doc = _json(path)
    if not path.is_file() or not isinstance(doc, dict):
        return ["缺少 fact-review.json；严格事实主张必须有独立语义核查回执"] if require else []
    errors: list[str] = []
    source_path = article / "sources.json"
    source_doc = _json(source_path)
    claims = source_doc.get("claims") if isinstance(source_doc, dict) else None
    if not isinstance(claims, list):
        return ["sources.json claims 无效，无法验证 fact-review"]
    if doc.get("contract") != CONTRACT:
        errors.append("fact-review.json contract 无效")
    if doc.get("status") != "passed":
        errors.append("fact-review.json status 必须为 passed；pending_human 不能进入内容审稿通过")
    if str(doc.get("reviewer_type", "")).strip().lower() != "human":
        errors.append("fact-review.json 必须由 reviewer_type=human 完成")
    for key in ("reviewer", "signed_by", "approval_event_id", "reviewed_at"):
        if not str(doc.get(key, "")).strip():
            errors.append(f"fact-review.json 缺少 {key}")
    if doc.get("sources_digest") != _sha256(source_path):
        errors.append("fact-review.json sources_digest 与当前 sources.json 不一致")
    expected_digest = _claims_digest([item for item in claims if isinstance(item, dict)])
    if doc.get("claims_digest") != expected_digest:
        errors.append("fact-review.json claims_digest 与当前 claim ledger 不一致")
    expected_ids = {str(item.get("id") or "") for item in claims if isinstance(item, dict)}
    records = doc.get("claims")
    if not isinstance(records, list):
        return errors + ["fact-review.json claims 必须是列表"]
    by_id = {str(item.get("claim_id") or ""): item for item in records if isinstance(item, dict)}
    for claim_id in sorted(expected_ids):
        record = by_id.get(claim_id)
        if not record:
            errors.append(f"fact-review 缺少 claim：{claim_id}")
            continue
        if record.get("verdict") not in REQUIRED_VERDICTS:
            errors.append(f"claim {claim_id} 未给出 supported/qualified/rejected verdict")
        if not str(record.get("evidence_excerpt") or "").strip():
            errors.append(f"claim {claim_id} 缺少人工核对的 evidence_excerpt")
        if record.get("scope_checked") is not True:
            errors.append(f"claim {claim_id} 未确认适用范围")
        if record.get("counterevidence_checked") is not True:
            errors.append(f"claim {claim_id} 未确认反证/限制")
    events = _json(article / "approval-events.json")
    if not isinstance(events, list):
        events = []
    event_ids = {
        str(event.get("event_id")): event
        for event in events
        if isinstance(event, dict)
    }
    event = event_ids.get(str(doc.get("approval_event_id")))
    if not event or event.get("subject") != "factual_review" or event.get("reviewer_type") != "human" or not str(event.get("signed_by", "")).strip():
        errors.append("approval_event_id 未指向 factual_review 的 human signed_by 事件")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--prepare", action="store_true", help="生成 pending_human 事实复核包")
    parser.add_argument("--check", action="store_true", help="校验人工填写的 passed 回执")
    args = parser.parse_args()
    article = resolve_article_workspace(args.article, allow_test_fixture=True)
    if args.prepare or not args.check:
        return prepare(article)
    errors = validate(article)
    if errors:
        print("FACT REVIEW BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("FACT REVIEW PASSED: independent human semantic receipt is complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
