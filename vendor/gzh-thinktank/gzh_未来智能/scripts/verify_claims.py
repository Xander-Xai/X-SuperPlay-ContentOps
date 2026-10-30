#!/usr/bin/env python3
"""Verify claim-to-evidence provenance for a research workspace.

This is a deterministic provenance checker, not a semantic fact checker. It
cannot decide whether a claim is true; it proves that every claim has a
declared locator and that the locator resolves to a source whose snapshot/hash
was independently recorded. Semantic review and human accountability remain
required for high-risk or benchmark claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "claim-verification-v1"
VERSION = "1.0.0"
LOCAL_KINDS = {"local_artifact", "reproduction", "test-fixture"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest_claims(claims: list[dict[str, Any]]) -> str:
    payload = json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_records(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id", "")).strip(): item
        for item in document.get("sources", [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }


def _verification_records(article_dir: Path) -> dict[str, dict[str, Any]]:
    document = _json(article_dir / "source-verification.json")
    if not isinstance(document, dict):
        return {}
    return {
        str(item.get("id", "")).strip(): item
        for item in document.get("sources", [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }


def _verify_locator(article_dir: Path, claim: dict[str, Any], source_map: dict[str, dict[str, Any]], verification_map: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    claim_id = str(claim.get("id", "")).strip() or "<missing-id>"
    refs = claim.get("source_ids")
    if not isinstance(refs, list) or not refs:
        return [f"{claim_id}: source_ids 不能为空"]
    source_ids = {str(item).strip() for item in refs if str(item).strip()}
    locator = claim.get("evidence_locator")
    locators = locator if isinstance(locator, list) else [locator]
    if not locators or any(not isinstance(item, dict) for item in locators):
        return [f"{claim_id}: evidence_locator 必须是对象或对象列表"]
    located_sources: set[str] = set()
    for item in locators:
        source_id = str(item.get("source_id", "")).strip()
        kind = str(item.get("kind", "")).strip()
        ref = str(item.get("ref", "")).strip()
        if not source_id or source_id not in source_ids:
            errors.append(f"{claim_id}: locator.source_id 必须来自 claim.source_ids")
            continue
        if not kind or not ref:
            errors.append(f"{claim_id}: locator 必须包含 kind 和 ref")
            continue
        if source_id not in source_map:
            errors.append(f"{claim_id}: locator 引用了不存在的来源 {source_id}")
            continue
        located_sources.add(source_id)
        source = source_map[source_id]
        source_kind = str(source.get("kind", "external")).strip().lower()
        if source_kind not in LOCAL_KINDS:
            record = verification_map.get(source_id)
            if not record or record.get("status") != "passed":
                errors.append(f"{claim_id}: 外部来源 {source_id} 没有 passed 验证回执")
            snapshot = str((record or {}).get("snapshot", "")).strip()
            if not snapshot or not (article_dir / snapshot).is_file():
                errors.append(f"{claim_id}: 外部来源 {source_id} 的 snapshot 不存在")
    missing = sorted(source_ids - located_sources)
    if missing:
        errors.append(f"{claim_id}: locator 未覆盖来源：{', '.join(missing)}")
    return errors


def verify(article_dir: Path) -> int:
    article_dir = article_dir.resolve()
    source_path = article_dir / "sources.json"
    output = article_dir / "claim-verification.json"
    document = _json(source_path)
    errors: list[str] = []
    claims = document.get("claims") if isinstance(document, dict) else None
    source_map = _source_records(document) if isinstance(document, dict) else {}
    verification_map = _verification_records(article_dir)
    if not source_path.is_file() or not isinstance(document, dict):
        errors.append("缺少或无法解析 sources.json")
        claims = []
    if not isinstance(claims, list) or not claims:
        errors.append("sources.json 必须包含 claims 列表")
        claims = []
    normalized_claims = [item for item in claims if isinstance(item, dict)]
    if len(normalized_claims) != len(claims):
        errors.append("claims 列表包含非对象项")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for claim in normalized_claims:
        claim_id = str(claim.get("id", "")).strip()
        claim_errors: list[str] = []
        if not claim_id:
            claim_errors.append("claim 缺少稳定 id")
        elif claim_id in seen:
            claim_errors.append(f"claim id 重复：{claim_id}")
        else:
            seen.add(claim_id)
        if not str(claim.get("statement", "")).strip():
            claim_errors.append(f"{claim_id or '<missing-id>'}: statement 不能为空")
        if not str(claim.get("claim_type", "")).strip():
            claim_errors.append(f"{claim_id or '<missing-id>'}: claim_type 不能为空")
        claim_errors.extend(_verify_locator(article_dir, claim, source_map, verification_map))
        records.append({
            "claim_id": claim_id,
            "status": "passed" if not claim_errors else "blocked",
            "source_ids": claim.get("source_ids", []),
            "errors": claim_errors,
            "verified_by": "verify_claims.py",
        })
        errors.extend(claim_errors)
    payload = {
        "schema_version": 1,
        "contract": CONTRACT,
        "verifier": "verify_claims.py",
        "verifier_version": VERSION,
        "status": "passed" if not errors else "blocked",
        "verified_at": _now(),
        "sources_digest": _sha256(source_path) if source_path.is_file() else "",
        "claims_digest": _digest_claims(normalized_claims),
        "records": records,
        "errors": errors,
        "semantic_truth_check": "not_performed",
    }
    article_dir.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("CLAIM VERIFY BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"CLAIM VERIFY PASSED: {len(records)} claims; semantic truth review remains separate")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    args = parser.parse_args()
    article_dir = args.article.expanduser()
    if not article_dir.is_absolute():
        article_dir = ROOT / article_dir
    return verify(article_dir)


if __name__ == "__main__":
    raise SystemExit(main())
