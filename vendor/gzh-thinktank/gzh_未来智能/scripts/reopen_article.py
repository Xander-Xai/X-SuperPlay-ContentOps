#!/usr/bin/env python3
"""Safely reopen an article for a corrected draft without editing state by hand."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workspace_paths import resolve_article_workspace  # noqa: E402

try:
    from checkpoint import create as create_checkpoint
except ImportError:  # pragma: no cover - direct import fallback for library users
    create_checkpoint = None


def yaml_load(path: Path) -> dict:
    try:
        import yaml

        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (ImportError, OSError, ValueError):
        return {}


def yaml_dump(path: Path, value: dict) -> None:
    import yaml

    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    try:
        article = resolve_article_workspace(args.article, allow_test_fixture=True)
    except ValueError as exc:
        print(f"REOPEN BLOCKED: {exc}")
        return 1
    state_path = article / "matrix-state.json"
    if not state_path.is_file():
        print("REOPEN BLOCKED: 缺少 matrix-state.json")
        return 1
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"REOPEN BLOCKED: 状态文件无效：{exc}")
        return 1
    old_stage = str(state.get("current_stage") or state.get("status") or "none")
    # Reopen is a state-changing operation.  Take a content-addressed snapshot
    # first so a mistaken reopen can be resumed without hand-editing state.
    if create_checkpoint is not None:
        checkpoint_status, _ = create_checkpoint(article, "before-reopen", args.reason)
        if checkpoint_status != 0:
            print("REOPEN BLOCKED: 无法创建 reopen 前 checkpoint")
            return 1
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = article / "snapshots" / "reopen" / timestamp
    archive_dir.mkdir(parents=True, exist_ok=True)
    receipt = article / "publish-receipt.json"
    if receipt.is_file():
        shutil.copy2(receipt, archive_dir / "publish-receipt.json")
    attempt = article / "publish-attempt.json"
    if attempt.is_file():
        shutil.copy2(attempt, archive_dir / "publish-attempt.json")
    receipt.write_text(json.dumps({"status": "pending", "mode": "draft"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    attempt.write_text(json.dumps({
        "schema_version": 1,
        "status": "pending",
        "mode": "draft",
        "account_slot": None,
        "media_id": "",
        "thumb_media_id": "",
        "created_at": "",
        "html_digest": "",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta_path = article / "article.yaml"
    if meta_path.is_file():
        meta = yaml_load(meta_path)
        meta.update({
            "publish_completed": False,
            "draft_submitted": False,
            "draft_verified": False,
            "public_published": False,
        })
        yaml_dump(meta_path, meta)
    state.update({
        # 保留原 schema_version（v4 工作区 reopen 后不能被降级为 3，
        # 否则 environment_ready 会因"必须使用带 routing.yaml 的 schema v4"失败）。
        "schema_version": max(int(state.get("schema_version", 0) or 0), 3),
        "status": "selected",
        "current_stage": "none",
        "gate_history": [],
        "reopened_from": old_stage,
        "reopened_at": datetime.now(timezone.utc).isoformat(),
        "reopen_reason": args.reason,
        "revision": int(state.get("revision", 0) or 0) + 1,
    })
    artifacts = list(state.get("artifacts", [])) if isinstance(state.get("artifacts"), list) else []
    for required in ("review-checks.json", "preview-capture.json", "publish-attempt.json"):
        if required not in artifacts:
            artifacts.append(required)
    state["artifacts"] = artifacts
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ARTICLE REOPENED: {article}")
    print(f"ARCHIVED: snapshots/reopen/{timestamp}/publish-receipt.json + publish-attempt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
