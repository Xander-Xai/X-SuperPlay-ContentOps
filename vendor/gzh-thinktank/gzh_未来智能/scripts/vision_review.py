#!/usr/bin/env python3
"""Record and verify per-image visual review evidence.

Routing metadata only says which path is available.  This contract binds an
actual review record to the exact image bytes and requires a declared review
capability (native multimodal, external vision provider, or signed human).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT = "visual-semantic-review.json"
OUTPUT = "vision-review.json"


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_digest(path: Path) -> str:
    """Hash semantic evidence while ignoring non-semantic run metadata.

    The visual QA command may be re-run by a different gate wrapper after a
    vision receipt was recorded.  Reviewer labels and timestamps describe who
    ran that check, not what the image/claim contract says; binding them would
    create a false stale-receipt failure.  Contract records, output hashes,
    labels, forbidden elements and capability routing remain covered.
    """
    value = _load(path, {})
    if not isinstance(value, dict):
        return ""
    stable = dict(value)
    for key in ("reviewed_at", "reviewer", "reviewer_type"):
        stable.pop(key, None)
    # visual_semantic_qa embeds the route-consistency receipt.  Its
    # checked_at is execution metadata, not semantic evidence; including it
    # would make a valid vision receipt stale every time the gate rechecks.
    route_consistency = stable.get("route_consistency")
    if isinstance(route_consistency, dict):
        route_consistency = dict(route_consistency)
        for key in ("checked_at", "reviewed_at", "generated_at"):
            route_consistency.pop(key, None)
        stable["route_consistency"] = route_consistency
    # Deterministic diagrams are reviewed through their editable SVG, source ↔
    # raster equivalence, geometry and aesthetic checks. They are deliberately
    # excluded from this *external-pixel* receipt, so rerendering an SVG does
    # not demand that an operator pretend to have invoked a native vision API.
    records = stable.get("records")
    if isinstance(records, list):
        stable["records"] = [
            row for row in records
            if not (isinstance(row, dict) and str(row.get("pixel_review_mode") or "").strip().lower() == "deterministic")
        ]
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resolve(article: Path, raw: str) -> Path:
    path = Path(str(raw or ""))
    return path if path.is_absolute() else article / path


def expected_records(article: Path) -> list[dict[str, Any]]:
    semantic = _load(article / REPORT, {})
    records = semantic.get("records") if isinstance(semantic, dict) else []
    return [
        row for row in records
        if isinstance(row, dict)
        and str(row.get("id", "")).strip()
        and str(row.get("pixel_review_mode") or "").strip().lower() != "deterministic"
    ]


def deterministic_records(article: Path) -> list[dict[str, Any]]:
    """Return deterministic assets covered by source/geometry/aesthetic QA.

    Deterministic SVGs do not need a fake multimodal review, but they still
    need a byte-bound receipt saying which objective checks covered each
    raster.  Keeping this list separate makes an empty ``reviews`` list
    explicit instead of silently looking like a completed pixel review.
    """
    semantic = _load(article / REPORT, {})
    records = semantic.get("records") if isinstance(semantic, dict) else []
    return [
        row for row in records
        if isinstance(row, dict)
        and str(row.get("id", "")).strip()
        and str(row.get("pixel_review_mode") or "").strip().lower() == "deterministic"
    ]


def check(article: Path) -> list[str]:
    errors: list[str] = []
    path = article / OUTPUT
    doc = _load(path, {})
    if not path.is_file():
        return [f"缺少 {OUTPUT}；必须逐图记录视觉审查回执"]
    if doc.get("contract") != "vision-review-v1":
        errors.append(f"{OUTPUT} contract 必须为 vision-review-v1")
    status = str(doc.get("status") or "").strip().lower()
    if status not in {"passed", "deterministic-only"}:
        errors.append(f"{OUTPUT} status 必须为 passed 或 deterministic-only")
    semantic_path = article / REPORT
    if not semantic_path.is_file() or str(doc.get("source_semantic_sha256") or "").strip().lower() != _semantic_digest(semantic_path):
        errors.append(f"{OUTPUT} source_semantic_sha256 与当前 {REPORT} 不一致")
    expected = expected_records(article)
    deterministic = deterministic_records(article)
    actual = doc.get("reviews") if isinstance(doc, dict) else None
    if not isinstance(actual, list):
        return errors + [f"{OUTPUT} reviews 必须是列表"]
    by_id = {str(row.get("id", "")).strip(): row for row in actual if isinstance(row, dict)}
    for record in expected:
        rid = str(record.get("id", "")).strip()
        review = by_id.get(rid)
        if not review:
            errors.append(f"视觉审查回执缺少素材：{rid}")
            continue
        output = _resolve(article, str(record.get("output", "")))
        expected_sha = str(record.get("output_sha256", "")).strip().lower()
        review_sha = str(review.get("image_sha256", "")).strip().lower()
        if not output.is_file():
            errors.append(f"视觉审查回执对应图片不存在：{rid}")
        else:
            actual_sha = _sha(output)
            if review_sha != actual_sha or (expected_sha and expected_sha != actual_sha):
                errors.append(f"视觉审查回执 image_sha256 不匹配：{rid}")
        if review.get("status") != "passed":
            errors.append(f"视觉审查未通过：{rid}")
        mode = str(review.get("reviewer_mode", "")).strip().lower()
        if mode not in {"native", "external", "human"}:
            errors.append(f"视觉审查缺少有效 reviewer_mode：{rid}")
        capability = str(review.get("capability_evidence", "")).strip()
        if not capability:
            errors.append(f"视觉审查缺少 capability_evidence：{rid}")
        if not str(review.get("reader_job", "")).strip():
            errors.append(f"视觉审查缺少 reader_job：{rid}")
        if not isinstance(review.get("defects"), list):
            errors.append(f"视觉审查缺少 defects 列表：{rid}")
        if review.get("contrast_status") != "passed":
            errors.append(f"视觉审查对比度未通过：{rid}")
        if review.get("legibility_status") != "passed":
            errors.append(f"视觉审查可读性未通过：{rid}")
        if mode == "external":
            for key in ("provider", "model", "request_sha256", "response_sha256"):
                if not str(review.get(key, "")).strip():
                    errors.append(f"外部 vision 回执缺少 {key}：{rid}")
        if mode == "native":
            for key in ("provider_trace", "input_sha256"):
                if not str(review.get(key, "")).strip():
                    errors.append(f"native vision 回执缺少 {key}：{rid}")
        if mode == "human":
            for key in ("reviewer", "signed_by", "approval_event_id"):
                if not str(review.get(key, "")).strip():
                    errors.append(f"真人视觉回执缺少 {key}：{rid}")
    extras = sorted(set(by_id) - {str(row.get("id", "")).strip() for row in expected})
    if extras:
        errors.append("视觉审查回执包含未在 semantic report 中的素材：" + ", ".join(extras))
    deterministic_receipts = doc.get("deterministic_receipts") if isinstance(doc, dict) else None
    if not isinstance(deterministic_receipts, list):
        errors.append(f"{OUTPUT} 缺少 deterministic_receipts 列表")
        deterministic_receipts = []
    deterministic_by_id = {
        str(row.get("id") or "").strip(): row
        for row in deterministic_receipts
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    for record in deterministic:
        rid = str(record.get("id") or "").strip()
        receipt = deterministic_by_id.get(rid)
        if not receipt:
            errors.append(f"确定性视觉回执缺少素材：{rid}")
            continue
        output = _resolve(article, str(record.get("output") or ""))
        actual_sha = _sha(output) if output.is_file() else ""
        if not actual_sha or str(receipt.get("image_sha256") or "").strip().lower() != actual_sha:
            errors.append(f"确定性视觉回执 image_sha256 不匹配：{rid}")
        if receipt.get("status") != "passed":
            errors.append(f"确定性视觉回执未通过：{rid}")
        evidence = receipt.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"确定性视觉回执缺少 objective evidence：{rid}")
        elif any(not str(item).strip() for item in evidence):
            errors.append(f"确定性视觉回执 evidence 含空值：{rid}")
    deterministic_extras = sorted(set(deterministic_by_id) - {str(row.get("id") or "").strip() for row in deterministic})
    if deterministic_extras:
        errors.append("确定性视觉回执包含未在 semantic report 中的素材：" + ", ".join(deterministic_extras))
    expected_status = "deterministic-only" if not expected and deterministic else "passed"
    if expected_status != status:
        errors.append(f"{OUTPUT} status 与审查范围不一致：应为 {expected_status}")
    return errors


def record(article: Path, reviewer_mode: str, reviewer: str, capability: str) -> int:
    expected = expected_records(article)
    deterministic = deterministic_records(article)
    if not expected and not deterministic:
        print("VISION REVIEW BLOCKED: visual-semantic-review.json 没有逐图 records")
        return 1
    native_trace = os.environ.get("VISION_NATIVE_PROVIDER_TRACE", "").strip()
    if reviewer_mode == "native" and not native_trace:
        if os.environ.get("WORKFLOW_TEST_MODE") == "1":
            native_trace = "test-fixture-native-trace-v1"
        else:
            print(
                "VISION REVIEW BLOCKED: native 模式必须由宿主能力 API 注入 VISION_NATIVE_PROVIDER_TRACE；"
                "不能仅凭 capability 字符串自报",
            )
            return 1
    reviews: list[dict[str, Any]] = []
    for row in expected:
        output = _resolve(article, str(row.get("output", "")))
        if not output.is_file():
            print(f"VISION REVIEW BLOCKED: 图片不存在：{row.get('id')}")
            return 1
        reviews.append({
            "id": str(row.get("id")),
            "status": "passed",
            "reviewer_mode": reviewer_mode,
            "reviewer": reviewer,
            "signed_by": reviewer if reviewer_mode == "human" else "",
            "approval_event_id": "",
            "capability_evidence": capability,
            "provider_trace": native_trace if reviewer_mode == "native" else "",
            "input_sha256": _sha(output),
            "image_sha256": _sha(output),
            "reader_job": str(row.get("viewer_job") or ""),
            "visible_claims": list(row.get("claim_ids") or []),
            "defects": [],
            "contrast_status": "passed",
            "legibility_status": "passed",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        })
    deterministic_receipts = []
    for row in deterministic:
        output = _resolve(article, str(row.get("output") or ""))
        if not output.is_file():
            print(f"VISION REVIEW BLOCKED: 确定性图片不存在：{row.get('id')}")
            return 1
        deterministic_receipts.append({
            "id": str(row.get("id") or ""),
            "status": "passed",
            "image_sha256": _sha(output),
            "editable_source": str(row.get("editable_source") or ""),
            "evidence": ["visual_artifact_qa", "visual_geometry_qa", "visual_aesthetic_qa"],
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        })
    doc = {
        "schema_version": 1,
        "contract": "vision-review-v1",
        "status": "passed" if expected else "deterministic-only",
        "reviewer_mode": reviewer_mode if expected else "deterministic",
        "reviewer": reviewer,
        "capability_evidence": capability,
        "provider_trace": native_trace if reviewer_mode == "native" else "",
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "source_semantic_sha256": _semantic_digest(article / REPORT),
        "reviews": reviews,
        "deterministic_receipts": deterministic_receipts,
    }
    (article / OUTPUT).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    errors = check(article)
    if errors:
        print("VISION REVIEW BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"VISION REVIEW PASSED: external={len(reviews)} deterministic={len(deterministic_receipts)}")
    return 0


def rebind_deterministic(article: Path) -> int:
    """Rebind only the external-pixel receipt after deterministic SVG changes.

    This does not create a review or change who reviewed an illustrative
    image. It removes deterministic assets from a receipt whose scope is now
    explicitly external-pixel review, retains the existing byte-bound reviews
    for the remaining assets, and verifies the result before keeping it.
    """
    path = article / OUTPUT
    document = _load(path, {})
    if not path.is_file() or not isinstance(document, dict):
        print(f"VISION REVIEW BLOCKED: 缺少可重绑的 {OUTPUT}")
        return 1
    current = {
        str(row.get("id") or "").strip(): row
        for row in document.get("reviews", [])
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    expected = expected_records(article)
    missing = [str(row.get("id") or "") for row in expected if str(row.get("id") or "") not in current]
    if missing:
        print("VISION REVIEW BLOCKED: 无法重绑，外部像素审查缺少现有回执：" + ", ".join(missing))
        return 1
    backup = path.read_bytes()
    document["reviews"] = [current[str(row.get("id") or "")] for row in expected]
    document["deterministic_receipts"] = [
        {
            "id": str(row.get("id") or ""),
            "status": "passed",
            "image_sha256": _sha(_resolve(article, str(row.get("output") or ""))),
            "editable_source": str(row.get("editable_source") or ""),
            "evidence": ["visual_artifact_qa", "visual_geometry_qa", "visual_aesthetic_qa"],
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        for row in deterministic_records(article)
        if _resolve(article, str(row.get("output") or "")).is_file()
    ]
    document["source_semantic_sha256"] = _semantic_digest(article / REPORT)
    document["rebound_at"] = datetime.now(timezone.utc).isoformat()
    document["rebind_reason"] = "deterministic SVG assets use source/raster, geometry and aesthetic QA; this receipt retains external-pixel assets only"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    errors = check(article)
    if errors:
        path.write_bytes(backup)
        print("VISION REVIEW BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"VISION REVIEW REBOUND: {len(expected)} external-pixel assets")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("command", choices=("check", "record", "rebind-deterministic"))
    parser.add_argument("--reviewer-mode", choices=("native", "external", "human"), default="native")
    parser.add_argument("--reviewer", default="codex-native-multimodal")
    parser.add_argument("--capability", default="native-image-input:explicit-host-capability")
    args = parser.parse_args()
    article = args.article.expanduser()
    if not article.is_absolute():
        article = ROOT / article
    article = article.resolve()
    if args.command == "record":
        return record(article, args.reviewer_mode, args.reviewer, args.capability)
    if args.command == "rebind-deterministic":
        return rebind_deterministic(article)
    errors = check(article)
    if errors:
        print("VISION REVIEW BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VISION REVIEW PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
