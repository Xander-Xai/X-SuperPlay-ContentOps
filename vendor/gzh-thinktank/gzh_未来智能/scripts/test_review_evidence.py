#!/usr/bin/env python3
"""Regression tests for the structured review receipt writer."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from article_integrity import stable_sha256_file  # noqa: E402

SCRIPT = ROOT / "scripts" / "write_review_evidence.py"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="review-evidence-") as raw:
        article = Path(raw)
        (article / "review-report.md").write_text(
            "内容审：通过。事实核验：通过。合规：通过。错别字：通过。AI 味：已完成人工修改。",
            encoding="utf-8",
        )
        (article / "article.md").write_text("# 测试定稿\n\n" + ("正文。" * 250), encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), "--article", str(article), "--approve"], cwd=ROOT)
        assert result.returncode == 0
        evidence = json.loads((article / "review-evidence.json").read_text(encoding="utf-8"))
        assert evidence["status"] == "passed"
        assert all(value == "passed" for value in evidence["checks"].values())
        assert evidence["digest_mode"] == "stable-text-v1"
        checks = json.loads((article / "review-checks.json").read_text(encoding="utf-8"))
        assert checks["digest_mode"] == "stable-text-v1"
        assert checks["article_digest"] == stable_sha256_file(article / "article.md")

        # Platform newline normalization must not invalidate a semantic
        # review receipt; a later substantive edit still changes the stable
        # digest and is caught by the gate.
        article_path = article / "article.md"
        article_path.write_bytes(article_path.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
        assert stable_sha256_file(article_path) == checks["article_digest"]

        # An explicit new approval must rebuild a stale receipt for changed
        # content instead of forcing the operator to delete JSON manually.
        article_path.write_text(article_path.read_text(encoding="utf-8") + "\n已补充审稿后的修订。\n", encoding="utf-8")
        rebuilt = subprocess.run([sys.executable, str(SCRIPT), "--article", str(article), "--approve"], cwd=ROOT)
        assert rebuilt.returncode == 0
        rebuilt_checks = json.loads((article / "review-checks.json").read_text(encoding="utf-8"))
        assert rebuilt_checks["article_digest"] == stable_sha256_file(article / "article.md")
        assert rebuilt_checks["article_digest"] != checks["article_digest"]

        # The production report template records each dimension as a section
        # with explicit ``- 通过`` bullets, not only as ``检查项: 通过``.
        (article / "review-report.md").write_text(
            "## 内容审查\n- 通过：范围清晰。\n\n"
            "## 事实核验\n- 通过：来源已绑定。\n\n"
            "## 合规与安全\n- 通过：无敏感信息。\n\n"
            "## 错别字与人工化表达\n- 通过：已完成人工修改。\n",
            encoding="utf-8",
        )
        section_report = subprocess.run([sys.executable, str(SCRIPT), "--article", str(article), "--approve"], cwd=ROOT)
        assert section_report.returncode == 0

        # A valid legacy raw receipt is readable for compatibility, but an
        # explicit approval must upgrade the stored structured receipt too.
        legacy = dict(rebuilt_checks)
        legacy.pop("digest_mode", None)
        legacy["article_digest"] = __import__("hashlib").sha256(article_path.read_bytes()).hexdigest()
        report_path = article / "review-report.md"
        legacy["report_digest"] = __import__("hashlib").sha256(report_path.read_bytes()).hexdigest()
        (article / "review-checks.json").write_text(json.dumps(legacy), encoding="utf-8")
        migrated = subprocess.run([sys.executable, str(SCRIPT), "--article", str(article), "--approve"], cwd=ROOT)
        assert migrated.returncode == 0
        migrated_checks = json.loads((article / "review-checks.json").read_text(encoding="utf-8"))
        assert migrated_checks["digest_mode"] == "stable-text-v1"

        (article / "review-report.md").write_text(
            "内容审：未通过。事实核验：通过。合规：通过。错别字：通过。AI 味：已完成人工修改。",
            encoding="utf-8",
        )
        blocked = subprocess.run([sys.executable, str(SCRIPT), "--article", str(article), "--approve"], cwd=ROOT)
        assert blocked.returncode == 1
    print("REVIEW EVIDENCE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
