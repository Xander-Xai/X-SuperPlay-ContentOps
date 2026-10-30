#!/usr/bin/env python3
"""Regression tests for the independent semantic fact-review receipt."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fact_review import prepare, validate


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="fact-review-") as raw:
        article = Path(raw)
        (article / "sources.json").write_text(json.dumps({
            "sources": [],
            "claims": [{"id": "c1", "statement": "某基准结果", "claim_type": "benchmark", "source_ids": [], "evidence_locator": {}}],
        }, ensure_ascii=False), encoding="utf-8")
        assert prepare(article) == 0
        assert validate(article)  # pending_human must block
        doc = json.loads((article / "fact-review.json").read_text(encoding="utf-8"))
        doc.update({
            "status": "passed", "reviewer": "editor-1", "signed_by": "editor-1(manual)",
            "approval_event_id": "evt-1", "reviewed_at": datetime.now(timezone.utc).isoformat(),
        })
        doc["claims"][0].update({
            "verdict": "qualified", "evidence_excerpt": "原始资料中的限定条件摘录",
            "scope_checked": True, "counterevidence_checked": True,
        })
        (article / "fact-review.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        (article / "approval-events.json").write_text(json.dumps([{
            "event_id": "evt-1", "subject": "factual_review", "reviewer_type": "human", "signed_by": "editor-1(manual)",
        }]), encoding="utf-8")
        assert validate(article) == []
    print("FACT REVIEW TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
