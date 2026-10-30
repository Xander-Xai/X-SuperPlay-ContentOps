#!/usr/bin/env python3
"""Regression tests for the post-approval workflow hardening contracts."""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from style_lint import check_html  # noqa: E402
from check_wechat_svg_compatibility import check as check_wechat_svg  # noqa: E402
from vision_review import check as check_vision_review, _semantic_digest  # noqa: E402
from workspace_hygiene import manifest_errors, workspace_errors  # noqa: E402
from workflow_gate import _refresh_pending_reader_packet  # noqa: E402


def test_workspace_blocks_old_recipe() -> None:
    with tempfile.TemporaryDirectory(prefix="hygiene-") as raw:
        root = Path(raw)
        (root / "scripts").mkdir()
        (root / "scripts" / "old.py").write_text("drafts/20260809-混合专家模型-moe-原理-训练与部署全解", encoding="utf-8")
        assert any("旧主题" in item for item in workspace_errors(root))


def test_manifest_detects_hash_drift() -> None:
    with tempfile.TemporaryDirectory(prefix="manifest-") as raw:
        root = Path(raw)
        (root / "a.txt").write_text("v1", encoding="utf-8")
        digest = hashlib.sha256(b"v1").hexdigest()
        doc = {"schema_version": 3, "files": [{"path": "a.txt", "size": 2, "sha256": digest}]}
        canonical = (json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        doc["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
        (root / "split-manifest.json").write_text(json.dumps(doc), encoding="utf-8")
        assert manifest_errors(root) == []
        (root / "a.txt").write_text("v2", encoding="utf-8")
        assert any("hash drift" in item for item in manifest_errors(root))


def test_vision_review_binds_image_bytes() -> None:
    with tempfile.TemporaryDirectory(prefix="vision-review-") as raw:
        article = Path(raw)
        image = article / "x.png"
        image.write_bytes(b"png-fixture")
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        (article / "visual-semantic-review.json").write_text(json.dumps({"records": [{"id": "body-01", "output": "x.png", "output_sha256": digest, "viewer_job": "看懂流程", "claim_ids": ["c1"]}]}), encoding="utf-8")
        (article / "vision-review.json").write_text(json.dumps({"contract": "vision-review-v1", "status": "passed", "reviewer_mode": "native", "capability_evidence": "native-image-input:test", "provider_trace": "test-fixture-native-trace-v1", "source_semantic_sha256": _semantic_digest(article / "visual-semantic-review.json"), "reviews": [{"id": "body-01", "status": "passed", "reviewer_mode": "native", "capability_evidence": "native-image-input:test", "provider_trace": "test-fixture-native-trace-v1", "input_sha256": digest, "image_sha256": digest, "reader_job": "看懂流程", "defects": [], "contrast_status": "passed", "legibility_status": "passed"}], "deterministic_receipts": []}), encoding="utf-8")
        assert check_vision_review(article) == []
        image.write_bytes(b"changed")
        assert any("sha256" in item for item in check_vision_review(article))


def test_vision_review_excludes_deterministic_svg_from_pixel_receipt() -> None:
    with tempfile.TemporaryDirectory(prefix="vision-deterministic-") as raw:
        article = Path(raw)
        image = article / "x.png"
        image.write_bytes(b"png-fixture")
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        report = {"records": [{"id": "body-01", "output": "x.png", "output_sha256": digest, "viewer_job": "看懂流程", "claim_ids": ["c1"], "pixel_review_mode": "deterministic"}]}
        (article / "visual-semantic-review.json").write_text(json.dumps(report), encoding="utf-8")
        (article / "vision-review.json").write_text(json.dumps({
            "contract": "vision-review-v1",
            "status": "deterministic-only",
            "source_semantic_sha256": _semantic_digest(article / "visual-semantic-review.json"),
            "reviews": [],
            "deterministic_receipts": [{
                "id": "body-01",
                "status": "passed",
                "image_sha256": digest,
                "evidence": ["visual_artifact_qa", "visual_geometry_qa", "visual_aesthetic_qa"],
            }],
        }), encoding="utf-8")
        assert check_vision_review(article) == []


def test_vision_review_ignores_semantic_reviewer_metadata() -> None:
    with tempfile.TemporaryDirectory(prefix="vision-metadata-") as raw:
        article = Path(raw)
        report = {"status": "passed", "reviewer_type": "agent", "reviewer": "first-run", "reviewed_at": "2026-08-10T00:00:00+00:00", "records": []}
        path = article / "visual-semantic-review.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        first = _semantic_digest(path)
        report["reviewer_type"] = "human"
        report["reviewer"] = "second-run"
        report["reviewed_at"] = "2026-08-10T00:01:00+00:00"
        path.write_text(json.dumps(report), encoding="utf-8")
        assert _semantic_digest(path) == first


def test_pending_reader_packet_rebinds_without_human_claim() -> None:
    with tempfile.TemporaryDirectory(prefix="reader-rebind-") as raw:
        article = Path(raw)
        (article / "article.md").write_text("# current article", encoding="utf-8")
        (article / "visual-contract.json").write_text(json.dumps({
            "contract": "visual-contract-v1",
            "units": [],
        }), encoding="utf-8")
        (article / "visual-depth-review.json").write_text(json.dumps({"status": "passed"}), encoding="utf-8")
        (article / "visual-reader-test.json").write_text(json.dumps({
            "contract": "visual-reader-test-v1",
            "status": "pending-human",
            "reviewer_id": "unassigned-human-reader",
            "responses": [],
            "article_sha256": "0" * 64,
            "visual_contract_sha256": "1" * 64,
            "visual_depth_review_sha256": "2" * 64,
        }), encoding="utf-8")
        assert _refresh_pending_reader_packet(article) == []
        rebound = json.loads((article / "visual-reader-test.json").read_text(encoding="utf-8"))
        assert rebound["status"] == "pending-human"
        assert rebound["responses"] == []
        assert rebound["article_sha256"] == hashlib.sha256((article / "article.md").read_bytes()).hexdigest()
        assert rebound["visual_contract_sha256"] == hashlib.sha256((article / "visual-contract.json").read_bytes()).hexdigest()
        assert rebound["visual_depth_review_sha256"] == hashlib.sha256((article / "visual-depth-review.json").read_bytes()).hexdigest()


def test_style_lint_blocks_dark_code() -> None:
    with tempfile.TemporaryDirectory(prefix="style-") as raw:
        path = Path(raw) / "article.html"
        path.write_text('<pre style="background:#172B3E;color:#fff">x</pre>', encoding="utf-8")
        assert check_html(path)
        path.write_text('<pre style="font-family:Consolas,monospace;background:#F1F4F5;color:#17324D">x</pre>', encoding="utf-8")
        assert check_html(path) == []


def test_style_lint_does_not_require_future_preview() -> None:
    with tempfile.TemporaryDirectory(prefix="style-stage-") as raw:
        article = Path(raw)
        (article / "article.html").write_text("<section>formatted</section>", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "style_lint.py"), "--article", str(article)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_wechat_svg_paste_profile_is_strict_but_renderer_compatible() -> None:
    with tempfile.TemporaryDirectory(prefix="wechat-svg-compat-") as raw:
        article = Path(raw)
        good = article / "good.svg"
        good.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80" viewBox="0 0 120 80">'
            '<metadata id="visual-geometry-contract">{{}}</metadata><rect x="0" y="0" width="120" height="80"/>'
            '<text x="10" y="20">静态答案</text></svg>',
            encoding="utf-8",
        )
        result = check_wechat_svg(good)
        assert result["status"] == "passed"
        assert any("metadata id" in warning for warning in result["warnings"])
        bad = article / "bad.svg"
        bad.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="80" viewBox="0 0 120 80">'
            '<script>alert(1)</script><g id="x" class="y"/></svg>',
            encoding="utf-8",
        )
        failed = check_wechat_svg(bad)
        assert failed["status"] == "failed"
        assert any("forbidden element" in error or "percentage geometry" in error for error in failed["errors"])


if __name__ == "__main__":
    test_workspace_blocks_old_recipe()
    test_manifest_detects_hash_drift()
    test_vision_review_binds_image_bytes()
    test_vision_review_excludes_deterministic_svg_from_pixel_receipt()
    test_vision_review_ignores_semantic_reviewer_metadata()
    test_pending_reader_packet_rebinds_without_human_claim()
    test_style_lint_blocks_dark_code()
    test_style_lint_does_not_require_future_preview()
    test_wechat_svg_paste_profile_is_strict_but_renderer_compatible()
    print("WORKFLOW HARDENING TESTS PASSED")
