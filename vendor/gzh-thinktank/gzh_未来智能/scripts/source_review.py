#!/usr/bin/env python3
"""Structured relevance/scope review for research sources.

This gate is deliberately different from ``verify_sources.py``:

* source verification proves that a URL/snapshot was fetched and fingerprinted;
* source review proves that an agent actually extracted a bounded summary,
  compared the source with the current topic, recorded limitations, and made
  an explicit include/conditional/exclude decision before the source can feed
  later evidence or claims.

It does not declare semantic truth.  High-risk, paper, benchmark, regulated,
or human-required claims still use the independent ``fact-review`` gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workspace_paths import resolve_article_workspace


CONTRACT = "source-review-v1"
VERDICTS = {"included", "conditional", "excluded"}
TOPIC_MATCHES = {"direct", "adjacent", "background", "none"}
EXTRACTION_METHODS = {"fulltext", "abstract", "summary", "snapshot", "metadata"}
MAX_EXCERPT_CHARS = 1200
MAX_SUMMARY_CHARS = 1600


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> bool:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except (TypeError, ValueError):
        return False


def _topic_fingerprint(article: Path) -> str:
    plan = _json(article / "evidence-plan.json")
    if isinstance(plan, dict):
        binding = plan.get("topic_binding")
        if isinstance(binding, dict) and str(binding.get("topic_fingerprint", "")).strip():
            return str(binding["topic_fingerprint"]).strip()
    contract = _json(article / "topic-contract.yaml")
    if isinstance(contract, dict):
        return str(contract.get("topic_fingerprint", "")).strip()
    return ""


def _source_map(article: Path) -> dict[str, dict[str, Any]]:
    doc = _json(article / "sources.json")
    return {
        str(item.get("id", "")).strip(): item
        for item in (doc.get("sources", []) if isinstance(doc, dict) else [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }


def _claims(article: Path) -> dict[str, dict[str, Any]]:
    doc = _json(article / "sources.json")
    return {
        str(item.get("id", "")).strip(): item
        for item in (doc.get("claims", []) if isinstance(doc, dict) else [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }


def _plan_map(article: Path) -> dict[str, dict[str, Any]]:
    doc = _json(article / "evidence-plan.json")
    return {
        str(item.get("source_id", "")).strip(): item
        for item in (doc.get("sources", []) if isinstance(doc, dict) else [])
        if isinstance(item, dict) and str(item.get("source_id", "")).strip()
    }


def _default_record(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": str(source.get("id", "")).strip(),
        "source_title": str(source.get("title", "")).strip(),
        "source_type": str(source.get("evidence_level", "")).strip(),
        "review_verdict": "pending",
        "topic_match": "none",
        "extraction": {
            "method": "",
            "locator": "",
            "source_path": "",
            "excerpt": "",
            "excerpt_sha256": "",
            "captured_at": "",
        },
        "extracted_summary": "",
        "support_scope": "",
        "claim_ids": [],
        "limitations": "",
        "review_rationale": "",
        "exclusion_reason": "",
    }


def init(article: Path) -> int:
    sources = _source_map(article)
    if not sources:
        print("SOURCE REVIEW BLOCKED: sources.json 没有可审查来源")
        return 1
    payload = {
        "schema_version": 1,
        "contract": CONTRACT,
        "status": "pending",
        "review_method": "structured-source-scope-review-v1",
        "reviewer_type": "agent",
        "reviewer": "",
        "reviewed_at": "",
        "sources_digest": _sha256(article / "sources.json"),
        "topic_fingerprint": _topic_fingerprint(article),
        "semantic_truth_boundary": "本回执只证明来源相关性、摘要提取和适用范围已审查，不证明主张语义真值。",
        "sources": [_default_record(sources[sid]) for sid in sorted(sources)],
    }
    (article / "source-review.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"SOURCE REVIEW TEMPLATE CREATED: {len(sources)} sources; status=pending")
    return 0


def _validate_extraction(article: Path, source_id: str, record: dict[str, Any], errors: list[str]) -> None:
    extraction = record.get("extraction")
    if not isinstance(extraction, dict):
        errors.append("extraction 必须是对象")
        return
    method = str(extraction.get("method", "")).strip().lower()
    if method not in EXTRACTION_METHODS:
        errors.append("extraction.method 必须是 fulltext/abstract/summary/snapshot/metadata")
    for key in ("locator", "source_path", "excerpt", "excerpt_sha256", "captured_at"):
        if not str(extraction.get(key, "")).strip():
            errors.append(f"extraction 缺少 {key}")
    excerpt = str(extraction.get("excerpt", ""))
    if len(excerpt) > MAX_EXCERPT_CHARS:
        errors.append(f"extraction.excerpt 超过 {MAX_EXCERPT_CHARS} 字符")
    if excerpt and str(extraction.get("excerpt_sha256", "")).lower() != hashlib.sha256(excerpt.encode("utf-8")).hexdigest():
        errors.append("extraction.excerpt_sha256 与 excerpt 不一致")
    if not _iso(extraction.get("captured_at")):
        errors.append("extraction.captured_at 不是有效 ISO 时间")
    raw_source = str(extraction.get("source_path", "")).strip().replace("\\", "/")
    source_path = (article / raw_source).resolve()
    try:
        source_path.relative_to(article.resolve())
    except ValueError:
        errors.append(f"来源 {source_id} extraction.source_path 越出文章工作区")
        return
    if not source_path.is_file():
        errors.append(f"来源 {source_id} extraction.source_path 文件不存在：{raw_source}")
        return
    verification = _json(article / "source-verification.json")
    records = verification.get("sources", []) if isinstance(verification, dict) else []
    verified = next(
        (item for item in records if isinstance(item, dict) and str(item.get("id", "")).strip() == source_id),
        None,
    )
    expected_snapshot = str(verified.get("snapshot", "")).strip().replace("\\", "/") if isinstance(verified, dict) else ""
    if expected_snapshot and expected_snapshot != raw_source:
        errors.append(f"来源 {source_id} extraction.source_path 未绑定 source-verification 快照：{raw_source}")
    try:
        source_text = source_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        normalized_excerpt = excerpt.replace("\r\n", "\n").replace("\r", "\n")
        if normalized_excerpt not in source_text:
            errors.append(f"来源 {source_id} 的 extracted excerpt 不是 source-verification 快照原文子串")
    except OSError as exc:
        errors.append(f"来源 {source_id} 无法读取 source_path：{exc}")


def validate(article: Path) -> list[str]:
    errors: list[str] = []
    path = article / "source-review.json"
    doc = _json(path)
    sources = _source_map(article)
    claims = _claims(article)
    plan = _plan_map(article)
    if not path.is_file() or not isinstance(doc, dict):
        return ["缺少 source-review.json；必须先完成来源相关性审查"]
    if doc.get("contract") != CONTRACT:
        errors.append(f"source-review.json contract 必须是 {CONTRACT}")
    if doc.get("status") != "passed":
        errors.append("source-review.json status 必须是 passed；pending 来源不能进入后续写作")
    if doc.get("review_method") != "structured-source-scope-review-v1":
        errors.append("source-review.json 缺少结构化来源审查方法")
    if str(doc.get("reviewer_type", "")).strip().lower() not in {"agent", "human"}:
        errors.append("source-review.json reviewer_type 必须是 agent 或 human")
    if not str(doc.get("reviewer", "")).strip():
        errors.append("source-review.json 缺少 reviewer")
    if not _iso(doc.get("reviewed_at")):
        errors.append("source-review.json 缺少有效 reviewed_at")
    if doc.get("sources_digest") != _sha256(article / "sources.json"):
        errors.append("source-review.json sources_digest 与当前 sources.json 不一致")
    expected_topic = _topic_fingerprint(article)
    if expected_topic and doc.get("topic_fingerprint") != expected_topic:
        errors.append("source-review.json topic_fingerprint 与当前主题证据绑定不一致")
    records = doc.get("sources")
    if not isinstance(records, list):
        return errors + ["source-review.json sources 必须是列表"]
    by_id = {
        str(item.get("source_id", "")).strip(): item
        for item in records
        if isinstance(item, dict) and str(item.get("source_id", "")).strip()
    }
    missing = sorted(set(sources) - set(by_id))
    extra = sorted(set(by_id) - set(sources))
    if missing:
        errors.append("source-review.json 缺少来源审查记录：" + ", ".join(missing))
    if extra:
        errors.append("source-review.json 包含 sources.json 未声明来源：" + ", ".join(extra))

    for source_id, record in by_id.items():
        if source_id not in sources:
            continue
        verdict = str(record.get("review_verdict", "")).strip().lower()
        match = str(record.get("topic_match", "")).strip().lower()
        if verdict not in VERDICTS:
            errors.append(f"来源 {source_id} review_verdict 必须是 included/conditional/excluded")
        if match not in TOPIC_MATCHES:
            errors.append(f"来源 {source_id} topic_match 无效")
        _validate_extraction(article, source_id, record, errors)
        summary = str(record.get("extracted_summary", "")).strip()
        scope = str(record.get("support_scope", "")).strip()
        limitations = str(record.get("limitations", "")).strip()
        rationale = str(record.get("review_rationale", "")).strip()
        if len(summary) < 40:
            errors.append(f"来源 {source_id} 缺少足够的 extracted_summary（至少40字符）")
        if len(summary) > MAX_SUMMARY_CHARS:
            errors.append(f"来源 {source_id} extracted_summary 超过 {MAX_SUMMARY_CHARS} 字符")
        if len(scope) < 20:
            errors.append(f"来源 {source_id} 缺少明确 support_scope")
        if len(limitations) < 20:
            errors.append(f"来源 {source_id} 缺少 limitations；审查不能只写结论")
        if len(rationale) < 20:
            errors.append(f"来源 {source_id} 缺少 review_rationale")
        claim_ids = record.get("claim_ids")
        if not isinstance(claim_ids, list):
            errors.append(f"来源 {source_id} claim_ids 必须是列表")
            claim_ids = []
        unknown_claims = sorted(set(str(x).strip() for x in claim_ids) - set(claims))
        if unknown_claims:
            errors.append(f"来源 {source_id} 引用了不存在 claim：" + ", ".join(unknown_claims))
        if verdict == "excluded":
            if match != "none":
                errors.append(f"来源 {source_id} excluded 时 topic_match 必须是 none")
            if len(str(record.get("exclusion_reason", "")).strip()) < 20:
                errors.append(f"来源 {source_id} excluded 缺少 exclusion_reason")
            if claim_ids:
                errors.append(f"来源 {source_id} excluded 不能绑定 claim_ids")
        else:
            if match == "none":
                errors.append(f"来源 {source_id} included/conditional 不能是 topic_match=none")
            if str(record.get("extraction", {}).get("method", "")).strip().lower() == "metadata":
                errors.append(f"来源 {source_id} 只有 metadata 不能作为 included/conditional 依据")
            if not claim_ids:
                errors.append(f"来源 {source_id} included/conditional 必须绑定至少一个 claim_id")

    for source_id, row in plan.items():
        record = by_id.get(source_id)
        if not record:
            continue
        used = bool(row.get("used_in_article"))
        verdict = str(record.get("review_verdict", "")).strip().lower()
        reviewed_claims = set(str(x).strip() for x in record.get("claim_ids", []) if str(x).strip())
        planned_claims = set(str(x).strip() for x in row.get("claim_ids", []) if str(x).strip())
        if used and verdict not in {"included", "conditional"}:
            errors.append(f"正文采用来源 {source_id} 但来源审查 verdict 不是 included/conditional")
        if used and not (reviewed_claims & planned_claims):
            errors.append(f"正文采用来源 {source_id} 的审查 claim 映射与 evidence-plan 不重合")
        if not used and verdict == "included":
            errors.append(f"来源 {source_id} 审查为 included 但 evidence-plan 未标记 used_in_article=true；请明确采用或排除")

    for claim_id, claim in claims.items():
        for source_id in claim.get("source_ids", []) if isinstance(claim.get("source_ids"), list) else []:
            record = by_id.get(str(source_id).strip())
            if record and str(record.get("review_verdict", "")).strip().lower() == "excluded":
                errors.append(f"claim {claim_id} 引用了被来源审查排除的来源 {source_id}")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--init", action="store_true", help="生成待填写来源审查模板")
    parser.add_argument("--audit", action="store_true", help="审查 source-review.json")
    args = parser.parse_args()
    article = resolve_article_workspace(args.article, allow_test_fixture=True)
    if args.init:
        return init(article)
    errors = validate(article)
    if errors:
        print("SOURCE REVIEW BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"SOURCE REVIEW PASSED: {len(_source_map(article))} sources reviewed; relevance/scope receipt is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
