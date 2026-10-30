#!/usr/bin/env python3
"""Append-only typed approval-event ledger for human-in-the-loop decisions.

A3（对抗审查加固）：批准从“改一个字段”变成“追加一条有身份、有范围、
有时间、有摘要哈希的事件”。门禁不再信任 review-checks / visual-brief 里
自报的 reviewer_type=human，而是要求存在对应的 human approval event，
且 ``signed_by`` 非空（人为触发，不能由 agent 默认值冒充）。

用法：
    python scripts/record_approval.py --article <d> --subject cover_selection \
        --reviewer-type agent --reviewer e2e-regression-agent --scope visual-brief.yaml
    python scripts/record_approval.py --article <d> --subject factual_review \
        --reviewer-type human --reviewer "编辑-张三" --signed-by "张三(人工命令)" \
        --scope review-checks.json --summary "已逐条核对 claims 与来源快照"

事件文件：<article_dir>/approval-events.json（append-only；不覆盖历史事件）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
_sys.path.insert(0, str(ROOT / "scripts"))
from workflow_security import ensure_article_path, load_json as strict_load_json  # noqa: E402
EVENTS_FILE = "approval-events.json"
KNOWN_SUBJECTS = {
    "topic_selection",
    "factual_review",
    "compliance_review",
    "cover_selection",
    "external_publish",
    "final_review",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_events(article_dir: Path) -> list[dict[str, Any]]:
    path = article_dir / EVENTS_FILE
    if not path.is_file():
        return []
    value = strict_load_json(path, default=[])
    return value if isinstance(value, list) else []


def approval_event_map(article_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Return {subject: [events...]} for gate consumption."""
    by_subject: dict[str, list[dict[str, Any]]] = {}
    for event in load_events(article_dir):
        if not isinstance(event, dict):
            continue
        subject = str(event.get("subject", "")).strip()
        if subject:
            by_subject.setdefault(subject, []).append(event)
    return by_subject


def _summary_sha256(summary: str) -> str:
    return hashlib.sha256(summary.encode("utf-8")).hexdigest()


def record(article_dir: Path, *, subject: str, reviewer_type: str, reviewer: str,
           scope: str, signed_by: str = "", summary: str = "", operator: str = "cli") -> int:
    try:
        article_dir = ensure_article_path(article_dir, allow_test_fixture=True)
    except ValueError as exc:
        print(f"APPROVAL BLOCKED: {exc}", file=sys.stderr)
        return 1
    subject = subject.strip().lower()
    if subject not in KNOWN_SUBJECTS:
        print(f"APPROVAL BLOCKED: 未知 subject {subject!r}；必须是 {'/'.join(sorted(KNOWN_SUBJECTS))}", file=sys.stderr)
        return 1
    reviewer_type = reviewer_type.strip().lower()
    if reviewer_type not in {"agent", "human"}:
        print("APPROVAL BLOCKED: reviewer_type 必须是 agent 或 human", file=sys.stderr)
        return 1
    if not reviewer.strip():
        print("APPROVAL BLOCKED: 缺少 reviewer 身份", file=sys.stderr)
        return 1
    if reviewer_type == "human" and not signed_by.strip():
        print("APPROVAL BLOCKED: human 批准必须提供 --signed-by（人工触发身份，不能由 agent 默认值冒充）", file=sys.stderr)
        return 1
    scope_names = [name.strip() for name in scope.split(",") if name.strip()]
    if not scope_names:
        print("APPROVAL BLOCKED: 缺少 --scope 审查范围", file=sys.stderr)
        return 1
    scope_hashes = {}
    for name in scope_names:
        path = article_dir / name
        if not path.is_file():
            print(f"APPROVAL BLOCKED: 审查范围内文件不存在：{name}", file=sys.stderr)
            return 1
        scope_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    event = {
        "schema_version": 1,
        "event_id": f"{subject}-{_now().replace(':', '').replace('-', '').replace('+', '').replace('.', '')}",
        "subject": subject,
        "reviewer_type": reviewer_type,
        "reviewer": reviewer.strip(),
        "signed_by": signed_by.strip() if reviewer_type == "human" else "",
        "scope": scope_names,
        "scope_sha256": scope_hashes,
        "summary_sha256": _summary_sha256(summary or f"{subject} approved by {reviewer.strip()}"),
        "reviewed_at": _now(),
        "operator": operator.strip() or "cli",
    }
    path = article_dir / EVENTS_FILE
    events = load_events(article_dir)
    events.append(event)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    print(f"APPROVAL RECORDED: {subject} by {reviewer.strip()} ({reviewer_type}) -> {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True)
    parser.add_argument("--subject", required=True, help=f"{'/'.join(sorted(KNOWN_SUBJECTS))}")
    parser.add_argument("--reviewer-type", required=True, choices=("agent", "human"))
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--signed-by", default="", help="human 批准的人工触发身份")
    parser.add_argument("--scope", required=True, help="逗号分隔的被审文件清单（相对文章目录）")
    parser.add_argument("--summary", default="")
    parser.add_argument("--operator", default="cli")
    args = parser.parse_args()
    article_dir = Path(args.article).expanduser()
    if not article_dir.is_absolute():
        article_dir = ROOT / article_dir
    return record(article_dir.resolve(), subject=args.subject, reviewer_type=args.reviewer_type,
                  reviewer=args.reviewer, scope=args.scope, signed_by=args.signed_by,
                  summary=args.summary, operator=args.operator)


if __name__ == "__main__":
    raise SystemExit(main())
