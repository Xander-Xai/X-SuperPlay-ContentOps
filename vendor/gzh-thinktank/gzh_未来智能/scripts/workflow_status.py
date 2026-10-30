#!/usr/bin/env python3
"""Emit an explicit checked/advanced/blocked workflow status summary."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATES = ("environment_ready", "topic_selected", "research_complete", "research_reviewed", "draft_complete", "content_reviewed", "formatted", "illustrated", "final_reviewed", "draft_submitted")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def build(article: Path) -> dict:
    state = load(article / "matrix-state.json", {})
    current = str(state.get("current_stage") or "none")
    try:
        current_index = GATES.index(current)
    except ValueError:
        current_index = -1
    history = state.get("gate_history") if isinstance(state.get("gate_history"), list) else []
    history_ids = {str(item.get("stage")) for item in history if isinstance(item, dict)}
    stages = []
    for index, gate in enumerate(GATES):
        if gate in history_ids or index <= current_index:
            status = "advanced"
        else:
            status = "not_advanced"
        stages.append({"stage": gate, "status": status, "checked_receipt": gate in history_ids})
    receipt = load(article / "publish-receipt.json", {})
    external = {
        "publish_mode": str(state.get("publish_mode") or "draft"),
        "draft_status": str(receipt.get("status") or "pending"),
        "side_effect_completed": receipt.get("status") == "draft_created_and_verified",
        "media_id_present": bool(str(receipt.get("media_id") or "").strip()),
    }
    return {
        "schema_version": 1,
        "contract": "workflow-status-v1",
        "article": article.name,
        "current_stage": current,
        "interpretation": "checked_receipt and advanced are separate; no file presence is treated as completion",
        "stages": stages,
        "external_effects": external,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    args = parser.parse_args()
    article = args.article.expanduser()
    if not article.is_absolute():
        article = ROOT / article
    article = article.resolve()
    output = article / "workflow-status.json"
    output.write_text(json.dumps(build(article), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WORKFLOW STATUS WRITTEN: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
