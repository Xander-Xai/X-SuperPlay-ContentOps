#!/usr/bin/env python3
"""Regression tests for checkpoint create/verify/resume."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from checkpoint import create, resume, verify


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="checkpoint-") as raw:
        article = Path(raw) / "article"
        article.mkdir()
        (article / "matrix-state.json").write_text(json.dumps({"schema_version": 4, "current_stage": "draft_complete"}), encoding="utf-8")
        target = article / "article.md"
        target.write_text("原始定稿", encoding="utf-8")
        status, root = create(article, "test", "回归测试")
        assert status == 0 and root is not None
        checkpoint_id = root.name
        assert verify(article, checkpoint_id) == 0
        target.write_text("被误改内容", encoding="utf-8")
        assert resume(article, checkpoint_id) == 0
        assert target.read_text(encoding="utf-8") == "原始定稿"
        (root / "files" / "article.md").write_text("篡改快照", encoding="utf-8")
        assert verify(article, checkpoint_id) == 1
    print("CHECKPOINT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
