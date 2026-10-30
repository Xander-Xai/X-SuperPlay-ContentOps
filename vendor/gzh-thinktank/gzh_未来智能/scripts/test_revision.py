#!/usr/bin/env python3
"""Regression tests for explicit new/reused content revision evidence."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("record_revision", ROOT / "scripts" / "record_revision.py")
assert SPEC and SPEC.loader
record_revision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(record_revision)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="revision-qa-") as raw:
        article = Path(raw) / "article"
        article.mkdir()
        (article / "draft.md").write_text("# 新稿\n\n正文。" * 100, encoding="utf-8")
        source = article.parent / "source.md"
        source.write_text("用户提供的旧稿材料", encoding="utf-8")
        assert record_revision.record(type("Args", (), {
            "article": str(article), "mode": "reused", "source": str(source),
            "source_note": None, "change_summary": "重写结论并补充可复现步骤",
            "operator": "test", "approve_reuse": True,
        })()) == 0
        manifest = json.loads((article / "content-revision.json").read_text(encoding="utf-8"))
        assert manifest["mode"] == "reused"
        assert manifest["reuse_approved"] is True
        assert manifest["source"]["hash_mode"] == "canonical-text"
        (article / "article.md").write_text("# 定稿\n\n" + ("正文。" * 100), encoding="utf-8")
        assert record_revision.finalize(type("Args", (), {"article": str(article)})()) == 0
        manifest = json.loads((article / "content-revision.json").read_text(encoding="utf-8"))
        assert len(manifest["draft_digest"]) == 64
        assert len(manifest["final_digest"]) == 64
    print("REVISION TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
