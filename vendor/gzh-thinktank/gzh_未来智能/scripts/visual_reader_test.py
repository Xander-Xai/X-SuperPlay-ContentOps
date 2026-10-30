#!/usr/bin/env python3
"""Create a reproducible reader-understanding receipt for visual contracts.

The default command creates a pending-human blind-test packet.  It never
claims that an agent understood the image.  A reviewer may provide a JSON
response file with explicit ``correct``/``score`` fields only together with a
separate ``visual-reader-approval-v1`` file; answers alone cannot turn the
receipt into ``passed``.
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
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from workflow_security import load_json as strict_load_json  # noqa: E402


CONTRACT = "visual-reader-test-v1"
RECEIPT = "visual-reader-test.json"


def _json(path: Path) -> dict[str, Any]:
    value = strict_load_json(path, default={})
    return value if isinstance(value, dict) else {}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _approval_errors(article: Path, answers_path: Path, approval_path: Path | None) -> tuple[list[str], dict[str, Any]]:
    if approval_path is None:
        return ["提供真人 answers 时必须同时提供独立 approval-file；不能只靠答案 JSON 自报通过"], {}
    approval_path = approval_path.resolve()
    if approval_path.parent == article.resolve():
        return ["reader approval-file 不能放在文章目录内；必须来自独立审阅环境"], {}
    approval = strict_load_json(approval_path, default={})
    if not isinstance(approval, dict):
        return ["reader approval-file 不是严格 JSON 对象或包含重复键"], {}
    errors: list[str] = []
    if approval.get("contract") != "visual-reader-approval-v1":
        errors.append("reader approval contract 无效")
    if approval.get("status") != "approved":
        errors.append("reader approval status 必须是 approved")
    if str(approval.get("reviewer_type") or "").strip().lower() != "human":
        errors.append("reader approval reviewer_type 必须是 human")
    if not str(approval.get("reviewer_id") or "").strip() or not str(approval.get("signed_by") or "").strip():
        errors.append("reader approval 必须包含 reviewer_id 与 signed_by")
    if not str(approval.get("approval_event_id") or "").strip():
        errors.append("reader approval 缺少 approval_event_id")
    if str(approval.get("article_sha256") or "").lower() != _sha(article / "article.md"):
        errors.append("reader approval article_sha256 与当前 article.md 不一致")
    if str(approval.get("answers_sha256") or "").lower() != _sha(answers_path):
        errors.append("reader approval answers_sha256 与答案文件不一致")
    if not str(approval.get("signed_at") or "").strip():
        errors.append("reader approval 缺少 signed_at")
    return errors, approval


def build_packet(
    article: Path,
    answers_path: Path | None,
    reviewer_id: str,
    approval_path: Path | None = None,
) -> dict[str, Any]:
    contract = _json(article / "visual-contract.json")
    units = [u for u in contract.get("units", []) if isinstance(u, dict) and str(u.get("id")) != "cover"]
    questions = [
        {
            "question_id": f"q-{index + 1:02d}",
            "unit_id": str(unit.get("id") or ""),
            "prompt": str(unit.get("reader_question") or unit.get("viewer_job") or ""),
            "expected_answer": str(unit.get("answer_sentence") or unit.get("purpose") or ""),
            "scoring_rubric": {
                "4": "准确指出实体、关系类型和条件，并能回答 expected_answer",
                "3": "回答核心机制，允许一个次要遗漏",
                "2": "只复述名词或顺序，未说明机制",
                "1": "与图/正文无关或明显错误",
                "0": "无法回答",
            },
            "claim_ids": [str(x) for x in unit.get("claim_ids", []) if str(x).strip()],
            "blind": True,
        }
        for index, unit in enumerate(units)
    ]
    responses: list[dict[str, Any]] = []
    status = "pending-human"
    review_mode = "blind-reader-packet"
    approval: dict[str, Any] = {}
    approval_errors: list[str] = []
    if answers_path:
        raw = _json(answers_path)
        candidate = raw.get("responses") if isinstance(raw.get("responses"), list) else []
        for response in candidate:
            if not isinstance(response, dict):
                continue
            item = {
                "question_id": str(response.get("question_id") or ""),
                "unit_id": str(response.get("unit_id") or ""),
                "condition": str(response.get("condition") or "current_visual"),
                "answer": str(response.get("answer") or ""),
                "correct": bool(response.get("correct")),
                "score": max(0, min(4, int(response.get("score", 0) or 0))),
                "reviewer_id": str(response.get("reviewer_id") or reviewer_id),
            }
            responses.append(item)
        review_mode = "blind-reader-recorded"
        approval_errors, approval = _approval_errors(article, answers_path, approval_path)
        if not approval_errors and len(responses) == len(questions) and responses and all(item["correct"] and item["score"] >= 3 for item in responses):
            status = "passed"
        else:
            status = "blocked" if approval_errors else "failed"
    scores = [int(item["score"]) for item in responses]
    condition_scores: dict[str, list[int]] = {}
    for item in responses:
        condition_scores.setdefault(str(item.get("condition") or "current_visual"), []).append(int(item["score"]))
    condition_means = {
        key: round(sum(values) / len(values), 3)
        for key, values in condition_scores.items()
        if values
    }
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "status": status,
        "review_mode": review_mode,
        "reviewer_id": reviewer_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "article": article.name,
        "article_sha256": _sha(article / "article.md"),
        "visual_contract_sha256": _sha(article / "visual-contract.json"),
        "visual_depth_review_sha256": _sha(article / "visual-depth-review.json"),
        "sample_size": len(responses),
        "question_count": len(questions),
        "threshold": {"min_score": 3, "max_score": 4, "all_questions_correct": True},
        "experiment_design": {
            "type": "three-arm-visual-deletion-test",
            "conditions": ["no_visual", "current_visual", "deep_visual"],
            "primary_outcome": "mean_score_by_condition",
            "secondary_outcome": "answer_time_seconds",
            "pre_registered_threshold": "deep_visual mean_score >= no_visual mean_score + 0.5 and >= 3.0",
            "status": "pre-registered-packet",
            "note": "未提供真人回答时不得推断信息增益；current_visual 是当前产物，deep_visual 是改版候选条件。",
        },
        "mean_score": round(sum(scores) / len(scores), 3) if scores else None,
        "mean_score_by_condition": condition_means,
        "questions": questions,
        "responses": responses,
        "approval": {
            "contract": approval.get("contract", ""),
            "approval_event_id": approval.get("approval_event_id", ""),
            "reviewer_id": approval.get("reviewer_id", ""),
            "signed_by": approval.get("signed_by", ""),
            "signed_at": approval.get("signed_at", ""),
            "errors": approval_errors,
        },
        "note": "pending-human 是未完成的读者测试包；不得解释为真人或多模态审美批准。",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--answers", type=Path)
    parser.add_argument("--approval-file", type=Path, help="独立真人审阅批准文件；与 --answers 同时使用")
    parser.add_argument("--reviewer-id", default="unassigned-human-reader")
    args = parser.parse_args()
    article = args.article.resolve()
    report = build_packet(
        article,
        args.answers.resolve() if args.answers else None,
        args.reviewer_id,
        args.approval_file.resolve() if args.approval_file else None,
    )
    (article / RECEIPT).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "sample_size": report["sample_size"], "question_count": report["question_count"]}, ensure_ascii=False))
    return 0 if report["status"] in {"pending-human", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
