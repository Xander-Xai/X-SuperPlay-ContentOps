#!/usr/bin/env python3
"""Validate the explanatory depth contract for deterministic article visuals.

This is deliberately separate from pixel/label QA.  The existing visual QA
proves that an editable source contains expected labels and that the raster is
usable; this checker proves that a visual unit declares a reader question,
typed relations, claim/evidence bindings, and a machine-readable fallback.
Reader testing remains a human/POC layer and is recorded as pending-human until
the workflow has a signed reader-test receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT = "visual-depth-review.json"
CONTRACT_NAME = "visual-depth-contract-v1"
REQUIRED_UNIT_FIELDS = (
    "reader_question",
    "answer_sentence",
    "visual_thesis",
    "entities",
    "relations",
    "claim_ids",
    "evidence_ids",
    "layout_grammar",
    "must_explain",
    "fallback_backend",
    "fallback_trigger",
    "fallback_semantic_equivalence",
)
RELATION_FIELDS = (
    "id",
    "type",
    "source",
    "target",
    "evidence_ids",
    "source_locator",
    "verification_status",
)
GENERIC_TYPES = {"related", "connects", "next", "relationship", "flow"}


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _check_unit(unit: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    ident = str(unit.get("id") or "")
    errors: list[str] = []
    for field in REQUIRED_UNIT_FIELDS:
        value = unit.get(field)
        if field in {"entities", "relations", "claim_ids", "evidence_ids", "must_explain"}:
            if not isinstance(value, list) or not value:
                errors.append(f"{ident}: 缺少非空 {field}")
        elif not str(value or "").strip():
            errors.append(f"{ident}: 缺少 {field}")

    entities = {str(item).strip() for item in _as_list(unit.get("entities")) if str(item).strip()}
    claims = [str(item).strip() for item in _as_list(unit.get("claim_ids")) if str(item).strip()]
    evidence_ids = [str(item).strip() for item in _as_list(unit.get("evidence_ids")) if str(item).strip()]
    relations = _as_list(unit.get("relations"))
    relation_types: list[str] = []
    verified_count = 0
    evidence_bound_count = 0
    for relation in relations:
        if not isinstance(relation, dict):
            errors.append(f"{ident}: relations 含非对象值")
            continue
        for field in RELATION_FIELDS:
            value = relation.get(field)
            if field == "evidence_ids":
                if not isinstance(value, list) or not value:
                    errors.append(f"{ident}: relation {relation.get('id', '')} 缺少 evidence_ids")
            elif not str(value or "").strip():
                errors.append(f"{ident}: relation {relation.get('id', '')} 缺少 {field}")
        relation_type = str(relation.get("type") or "").strip().lower()
        if relation_type:
            relation_types.append(relation_type)
        if relation_type in GENERIC_TYPES:
            errors.append(f"{ident}: 禁止泛化关系类型 {relation_type}")
        if str(relation.get("verification_status") or "").strip().lower() != "verified":
            errors.append(f"{ident}: relation {relation.get('id', '')} 不是 verified")
        else:
            verified_count += 1
        if isinstance(relation.get("evidence_ids"), list) and relation.get("source_locator"):
            evidence_bound_count += 1
        source = str(relation.get("source") or "").strip()
        target = str(relation.get("target") or "").strip()
        if source and source not in entities:
            errors.append(f"{ident}: relation {relation.get('id', '')} source 不在 entities: {source}")
        if target and target not in entities:
            errors.append(f"{ident}: relation {relation.get('id', '')} target 不在 entities: {target}")

    if len(relations) < 3:
        errors.append(f"{ident}: typed relations 少于 3 条")
    must_explain = {str(item).strip().lower() for item in _as_list(unit.get("must_explain")) if str(item).strip()}
    missing_explain = sorted(must_explain - set(relation_types))
    if missing_explain:
        errors.append(f"{ident}: must_explain 未被 relation types 覆盖: {', '.join(missing_explain)}")
    if not claims:
        errors.append(f"{ident}: claim_ids 为空")
    if not evidence_ids:
        errors.append(f"{ident}: evidence_ids 为空")
    if str(unit.get("fallback_backend") or "").strip().lower() == str(unit.get("execution_backend") or "").strip().lower():
        # Same-backend fallback is allowed for a deterministic renderer, but
        # it must be explicit rather than pretending that a fallback was tested.
        if "same backend" not in str(unit.get("fallback_semantic_equivalence") or "").lower():
            errors.append(f"{ident}: fallback_backend 与 execution_backend 相同，必须声明 same backend 等价语义")

    record = {
        "id": ident,
        "claim_ids": claims,
        "evidence_ids": evidence_ids,
        "relation_count": len(relations),
        "verified_relation_count": verified_count,
        "relation_types": sorted(set(relation_types)),
        "evidence_bound_relation_count": evidence_bound_count,
        "structural_score": 4 if not errors else 0,
        "reader_test_status": "pending-human",
        "status": "passed" if not errors else "failed",
    }
    return record, errors


def check(article: Path) -> int:
    article = article.resolve()
    contract_path = article / "visual-contract.json"
    contract = _json(contract_path)
    errors: list[str] = []
    units = [
        unit for unit in _as_list(contract.get("units"))
        if isinstance(unit, dict) and str(unit.get("id") or "") != "cover"
    ]
    if contract.get("contract") != "visual-contract-v1":
        errors.append("visual-contract.json 必须保持 visual-contract-v1 兼容")
    if not units:
        errors.append("没有正文视觉单元")
    records: list[dict[str, Any]] = []
    all_claims: set[str] = set()
    for unit in units:
        record, unit_errors = _check_unit(unit)
        records.append(record)
        errors.extend(unit_errors)
        all_claims.update(record["claim_ids"])
    sources = _json(article / "sources.json")
    declared_claims = {
        str(item.get("id") or "").strip()
        for item in _as_list(sources.get("claims"))
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    if declared_claims and all(re.fullmatch(r"c\d+", value) for value in declared_claims):
        missing_claims = sorted(declared_claims - all_claims)
        if missing_claims:
            errors.append("正文视觉未覆盖 sources.json claim_ids: " + ", ".join(missing_claims))
    # The production workflow's paper/source ledger uses the stable c1/c2…
    # namespace.  Network-free fixtures may intentionally use an independent
    # claim namespace (for example claim-01) while testing only geometry;
    # preserve that fixture contract without weakening the production ledger.
    if declared_claims and all(re.fullmatch(r"c\d+", value) for value in declared_claims):
        unknown_claims = sorted(all_claims - declared_claims)
        if unknown_claims:
            errors.append("正文视觉引用了 sources.json 未声明的 claim_ids: " + ", ".join(unknown_claims))
    report = {
        "schema_version": 1,
        "contract": CONTRACT_NAME,
        "status": "passed" if not errors else "failed",
        "article": article.name,
        "article_sha256": _sha(article / "article.md"),
        "visual_contract_sha256": _sha(contract_path),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "review_mode": "structural-contract",
        "reader_test_status": "pending-human",
        "reader_test_receipt": {
            "path": "visual-reader-test.json",
            "status": str(_json(article / "visual-reader-test.json").get("status") or "missing"),
            "sample_size": int(_json(article / "visual-reader-test.json").get("sample_size", 0) or 0),
        },
        "records": records,
        "claim_coverage": sorted(all_claims),
        "errors": errors,
        "note": "结构深度检查通过不等于真人 reader test 通过；reader_test_status 必须单独签名。",
    }
    (article / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("VISUAL DEPTH QA BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"VISUAL DEPTH QA PASSED: {len(records)} units; reader_test=pending-human")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("command", nargs="?", default="check", choices=("check",))
    args = parser.parse_args()
    return check(args.article)


if __name__ == "__main__":
    raise SystemExit(main())
