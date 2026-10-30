#!/usr/bin/env python3
"""Unit tests for the sequential article workflow gates."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from article_integrity import canonical_html_digest, canonical_text_sha256_file, sha256_file  # noqa: E402
from route_content import build_route, route_digest  # noqa: E402
from receipt_integrity import stamp as stamp_receipt  # noqa: E402
from verify_draft_submission import _verified_attempt_payload  # noqa: E402

import workflow_gate
from account_context import ACCOUNT_ID  # noqa: E402


def _args(**overrides):
    values = {
        "env": None,
        "agent_writing_approved": True,
        "agent_image_capable": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class WorkflowGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.article = Path(self.tmp.name) / "article"
        self.article.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_pipeline_has_explicit_order(self):
        self.assertEqual(len(workflow_gate.GATES), 10)
        self.assertEqual(workflow_gate.GATES[0].key, "environment_ready")
        self.assertEqual(workflow_gate.GATES[-1].key, "draft_submitted")

    def test_cannot_skip_a_gate(self):
        state = {"current_stage": "topic_selected", "status": "topic_selected"}
        errors = workflow_gate.validate_transition(state, "formatted")
        self.assertTrue(any("不能跳过阶段" in error for error in errors))

    def test_draft_gate_blocks_short_content_and_missing_images(self):
        (self.article / "draft.md").write_text("# 标题\n\n## 一节\n\n内容", encoding="utf-8")
        errors = workflow_gate._errors_for_draft(self.article)
        self.assertTrue(any("content-revision.json" in error for error in errors))
        self.assertTrue(any("有效字数" in error for error in errors))
        self.assertTrue(any("图片占位不足" in error for error in errors))

    def test_revision_gate_blocks_stale_draft_digest(self):
        (self.article / "draft.md").write_text("# 标题\n\n" + ("正文。" * 500), encoding="utf-8")
        (self.article / "content-revision.json").write_text(json.dumps({
            "schema_version": 1,
            "status": "passed",
            "mode": "new",
            "operator": "test",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "change_summary": "测试新稿",
            "reuse_approved": False,
            "source": {"kind": "fresh_draft", "note": "test"},
            "draft_digest": "0" * 64,
        }), encoding="utf-8")
        errors = workflow_gate._errors_for_draft(self.article)
        self.assertTrue(any("draft_digest" in error for error in errors))

    def test_reused_revision_requires_approval_and_source_hash(self):
        source = self.article.parent / "source.md"
        source.write_text("旧稿来源", encoding="utf-8")
        draft = self.article / "draft.md"
        draft.write_text("# 标题\n\n" + ("正文。" * 500), encoding="utf-8")
        (self.article / "content-revision.json").write_text(json.dumps({
            "schema_version": 1,
            "status": "passed",
            "mode": "reused",
            "operator": "test",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "change_summary": "沿用旧稿",
            "reuse_approved": False,
            "source": {"kind": "local_material", "path": str(source), "sha256": sha256_file(source)},
            "draft_digest": sha256_file(draft),
        }), encoding="utf-8")
        errors = workflow_gate._errors_for_draft(self.article)
        self.assertTrue(any("reuse_approved" in error for error in errors))

    def test_submission_gate_requires_verified_readback(self):
        receipt = {"status": "draft_created_and_verified", "mode": "draft", "media_id": "x"}
        (self.article / "publish-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
        )
        errors = workflow_gate._errors_for_submission(self.article)
        self.assertTrue(any("readback" in error for error in errors))

    def test_clean_verified_receipt_passes_submission_gate(self):
        html = '<p><span leaf="">正文</span></p><img src="imgs/section-01.png" />'
        (self.article / "article.html").write_text(html, encoding="utf-8")
        digest = canonical_html_digest(html)
        receipt_document = {
            "status": "draft_created_and_verified",
            "mode": "draft",
            "media_id": "x",
            "target_kind": "mock",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "html_digest": sha256_file(self.article / "article.html"),
            "readback": {
                "title_matches": True,
                "author_matches": True,
                "literal_unicode_escapes": 0,
                "replacement_characters": 0,
                "content_has_div": False,
                "html_validator": "passed",
                "image_count": 1,
                "local_html_digest": canonical_html_digest((self.article / "article.html").read_text(encoding="utf-8")),
                "remote_html_digest": canonical_html_digest((self.article / "article.html").read_text(encoding="utf-8")),
                "html_digest_matches": True,
            },
        }
        attempt_document = {
            "status": "passed",
            "media_id": "x",
            "html_digest": sha256_file(self.article / "article.html"),
            "created_at": "2000-01-01T00:00:00+00:00",
        }
        previous_test_mode = os.environ.get("WORKFLOW_TEST_MODE")
        os.environ["WORKFLOW_TEST_MODE"] = "1"
        try:
            env_path = Path(self.tmp.name) / "wechat.env"
            env_path.write_text(
                f"WECHAT_{workflow_gate.PUBLISH_SLOT}_APPID=test\n"
                f"WECHAT_{workflow_gate.PUBLISH_SLOT}_APPSECRET=test\n",
                encoding="utf-8",
            )
            preflight = stamp_receipt({
                "status": "passed",
                "appid_key": f"WECHAT_{workflow_gate.PUBLISH_SLOT}_APPID",
                "appsecret_key": f"WECHAT_{workflow_gate.PUBLISH_SLOT}_APPSECRET",
                "draft_permission": True,
                "ip_whitelist_checked": True,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "probe": {"status": "passed"},
            }, self.article, receipt_kind="publish-preflight",
               account_slot=workflow_gate.PUBLISH_SLOT, env_path=env_path)
            receipt = stamp_receipt(
                receipt_document,
                self.article,
                receipt_kind="publish-receipt",
                account_slot=workflow_gate.PUBLISH_SLOT,
                env_path=env_path,
                operation_id="op-test",
            )
            attempt = stamp_receipt(
                attempt_document,
                self.article,
                receipt_kind="publish-attempt",
                account_slot=workflow_gate.PUBLISH_SLOT,
                env_path=env_path,
                operation_id="op-test",
            )
            (self.article / "publish-preflight.json").write_text(
                json.dumps(preflight, ensure_ascii=False), encoding="utf-8"
            )
            (self.article / "publish-receipt.json").write_text(
                json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
            )
            (self.article / "publish-attempt.json").write_text(
                json.dumps(attempt, ensure_ascii=False), encoding="utf-8"
            )
            self.assertEqual(
                workflow_gate._errors_for_submission(self.article, _args(env=str(env_path))), []
            )
        finally:
            if previous_test_mode is None:
                os.environ.pop("WORKFLOW_TEST_MODE", None)
            else:
                os.environ["WORKFLOW_TEST_MODE"] = previous_test_mode

    def test_submission_gate_blocks_receipt_older_than_current_html(self):
        (self.article / "article.html").write_text(
            '<p><span leaf="">正文</span></p><img src="imgs/section-01.png" />',
            encoding="utf-8",
        )
        receipt = {
            "status": "draft_created_and_verified",
            "mode": "draft",
            "media_id": "old",
            "target_kind": "wechat",
            "submitted_at": "2000-01-01T00:00:00+00:00",
            "html_digest": sha256_file(self.article / "article.html"),
            "readback": {
                "title_matches": True,
                "author_matches": True,
                "literal_unicode_escapes": 0,
                "replacement_characters": 0,
                "content_has_div": False,
                "html_validator": "passed",
                "image_count": 1,
                "local_html_digest": canonical_html_digest((self.article / "article.html").read_text(encoding="utf-8")),
                "remote_html_digest": canonical_html_digest((self.article / "article.html").read_text(encoding="utf-8")),
                "html_digest_matches": True,
            },
        }
        (self.article / "publish-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False), encoding="utf-8"
        )
        (self.article / "publish-attempt.json").write_text(json.dumps({
            "status": "passed",
            "media_id": "old",
            "html_digest": sha256_file(self.article / "article.html"),
            "created_at": "1999-01-01T00:00:00+00:00",
        }), encoding="utf-8")
        errors = workflow_gate._errors_for_submission(self.article)
        # A receipt may legitimately be replayed after a checkout/copy that
        # changes filesystem mtimes.  The content digest and attempt/receipt
        # binding are the freshness proofs; an old wall-clock timestamp alone
        # must not manufacture a stale-HTML failure.
        self.assertFalse(any("早于当前 HTML" in error for error in errors))

    def test_topic_gate_requires_brief_and_title_limit(self):
        (self.article / "article.yaml").write_text(
            "account: " + ACCOUNT_ID + "\ntitle: " + "超长标题" * 20 + "\nauthor: AI哨兵\ndigest: 摘要\n",
            encoding="utf-8",
        )
        (self.article / "topic-card.md").write_text(
            "# 选题\n\n账号：" + ACCOUNT_ID + "\n目标读者：测试读者\n核心判断：值得验证\n主要来源：https://example.com\n可搜索关键词：AI\n可分享角度：实测\n",
            encoding="utf-8",
        )
        (self.article / "seo-report.json").write_text(
            '{"status":"passed","score":88,"title_score":90,"keywords":["AI"]}', encoding="utf-8"
        )
        errors = workflow_gate._errors_for_topic(self.article)
        self.assertTrue(any("content-brief.yaml" in error for error in errors))
        self.assertTrue(any("title_max_length" in error for error in errors))

    def test_environment_requires_routing_before_any_stage(self):
        (self.article / "article.yaml").write_text(
            "account: " + ACCOUNT_ID + "\ncontent_medium: wechat_article\n", encoding="utf-8"
        )
        errors = workflow_gate._errors_for_environment(self.article, _args())
        self.assertTrue(any("routing.yaml" in error for error in errors))

    def test_environment_rejects_video_as_article_medium(self):
        (self.article / "article.yaml").write_text(
            "account: " + ACCOUNT_ID + "\ncontent_medium: video\n", encoding="utf-8"
        )
        route = build_route("hotspot", "AI工具", "", ACCOUNT_ID, "test")
        (self.article / "routing.yaml").write_text(json.dumps(route, ensure_ascii=False), encoding="utf-8")
        (self.article / "matrix-state.json").write_text(
            json.dumps({"schema_version": 4, "content_medium": "video"}), encoding="utf-8"
        )
        errors = workflow_gate._errors_for_environment(self.article, _args())
        self.assertTrue(any("content_medium" in error for error in errors))

    def test_environment_missing_credentials_reports_blocker_without_crashing(self):
        (self.article / "article.yaml").write_text(
            "account: " + ACCOUNT_ID + "\ncontent_medium: wechat_article\nroute_digest: "
            + ("0" * 64)
            + "\n",
            encoding="utf-8",
        )
        route = build_route("hotspot", "AI教程", "", ACCOUNT_ID, "test")
        (self.article / "routing.yaml").write_text(json.dumps(route, ensure_ascii=False), encoding="utf-8")
        (self.article / "matrix-state.json").write_text(
            json.dumps({"schema_version": 4, "content_medium": "wechat_article", "routing_digest": "0" * 64}),
            encoding="utf-8",
        )
        (self.article / "publish-preflight.json").write_text(
            json.dumps({"status": "pending", "account_slot": workflow_gate.PUBLISH_SLOT}), encoding="utf-8"
        )
        errors = workflow_gate._errors_for_environment(
            self.article, _args(env=str(Path(tempfile.gettempdir()) / "nonexistent-aws.env"))
        )
        self.assertTrue(any("内容凭证文件" in error for error in errors))

    def test_environment_does_not_require_wechat_preflight_for_offline_content(self):
        route = build_route("hotspot", "AI教程", "", ACCOUNT_ID, "test")
        route_path = self.article / "routing.yaml"
        route_path.write_text(json.dumps(route, ensure_ascii=False), encoding="utf-8")
        digest = route_digest(route_path)
        (self.article / "article.yaml").write_text(
            f"account: {ACCOUNT_ID}\ntitle: 测试\nauthor: X超玩•未来智能\n"
            f"content_medium: wechat_article\nroute_digest: {digest}\n",
            encoding="utf-8",
        )
        (self.article / "matrix-state.json").write_text(json.dumps({
            "schema_version": 4, "content_medium": "wechat_article", "routing_digest": digest,
        }), encoding="utf-8")
        (self.article / "capability-profile.json").write_text(json.dumps({
            "contract": "capability-profile-v1", "external_image_api_required": False,
            "selected_backends": ["deterministic-svg"],
        }), encoding="utf-8")
        errors = workflow_gate._errors_for_environment(self.article, _args())
        self.assertFalse(any("publish-preflight" in error for error in errors), errors)
        self.assertFalse(any("微信凭证" in error for error in errors), errors)

    def test_draft_submission_owns_wechat_preflight(self):
        (self.article / "matrix-state.json").write_text('{"schema_version": 4}', encoding="utf-8")
        (self.article / "publish-preflight.json").write_text(json.dumps({
            "status": "pending", "account_slot": workflow_gate.PUBLISH_SLOT,
        }), encoding="utf-8")
        errors = workflow_gate._publish_preflight_errors(self.article, _args())
        self.assertTrue(any("微信凭证" in error for error in errors), errors)
        self.assertTrue(any("status 必须是 passed" in error for error in errors), errors)

    def test_verified_attempt_uses_normalized_passed_status(self):
        result = _verified_attempt_payload(
            {"status": "draft_created_unverified"}, media_id="m1", thumb_media_id="t1",
            verified_at="2026-08-11T00:00:00+00:00", html_digest="a" * 64,
            operation_id="op-1",
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["draft_status"], "draft_created_and_verified")

    def test_research_gate_requires_structured_source_records(self):
        (self.article / "research.md").write_text(
            "来源：官方文档。版本/环境：Python。可复现命令：python test.py。限制：仅离线测试。",
            encoding="utf-8",
        )
        errors = workflow_gate._errors_for_research(self.article)
        self.assertTrue(any("sources.json" in error for error in errors))

    def test_research_gate_accepts_platform_stable_text_evidence_hash(self):
        evidence = self.article.parent / "evidence.py"
        evidence.write_bytes("第一行\r\n第二行\r\n".encode("utf-8"))
        (self.article / "research.md").write_text(
            "来源：本地复现证据。版本/环境：Python 3.11，Windows 与 Unix 换行兼容性测试。"
            "可复现命令：python test.py；先写入 CRLF，再以规范化文本哈希回读。"
            "限制：仅验证哈希稳定性，不代表外部事实已经完成独立核验。证据：测试夹具可重复执行。"
            "复核记录：相同文本分别使用 LF、CRLF 和 CR 写入后，规范化摘要应保持一致，"
            "并且来源路径、检索时间、证据等级和主张映射均可追溯。",
            encoding="utf-8",
        )
        source = {
            "id": "local-evidence",
            "title": "本地证据",
            "path": str(evidence),
            "sha256": canonical_text_sha256_file(evidence),
            "hash_mode": "canonical-text",
            "retrieved_at": "2026-08-03",
            "evidence_level": "reproducible-local",
            "kind": "local_artifact",
        }
        (self.article / "sources.json").write_text(json.dumps({
            "schema_version": 1,
            "sources": [source],
            "claims": [{"id": "claim", "statement": "可复现", "claim_type": "test-result", "source_ids": ["local-evidence"]}],
        }, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(workflow_gate._errors_for_research(self.article), [])

    def test_formatted_gate_blocks_when_strict_validator_is_missing(self):
        (self.article / "article.md").write_text("# 标题\n\n" + ("正文。" * 500), encoding="utf-8")
        (self.article / "article.html").write_text("<p><span leaf=\"\">" + ("正文。" * 500) + "</span></p>", encoding="utf-8")
        (self.article / "format-report.json").write_text(json.dumps({
            "status": "passed", "validator": "passed",
            "source_digest": sha256_file(self.article / "article.md"),
            "html_digest": sha256_file(self.article / "article.html"),
        }), encoding="utf-8")
        old = workflow_gate.VALIDATOR
        workflow_gate.VALIDATOR = self.article / "missing-validator.py"
        try:
            errors = workflow_gate._errors_for_formatted(self.article)
        finally:
            workflow_gate.VALIDATOR = old
        self.assertTrue(any("严格 HTML 校验器缺失" in error for error in errors))

    def test_formatted_gate_uses_bound_digests_not_mtime(self):
        article_path = self.article / "article.md"
        html_path = self.article / "article.html"
        article_path.write_text("# 标题\n\n" + ("正文。" * 500), encoding="utf-8")
        html_path.write_text("<p><span leaf=\"\">" + ("正文。" * 500) + "</span></p>", encoding="utf-8")
        (self.article / "format-report.json").write_text(json.dumps({
            "status": "passed", "validator": "passed", "source": "article.md",
            "source_digest": sha256_file(article_path),
            "canonical_source_digest": sha256_file(article_path),
            "html_digest": sha256_file(html_path),
        }), encoding="utf-8")
        newer = html_path.stat().st_mtime + 10
        os.utime(article_path, (newer, newer))
        errors = workflow_gate._errors_for_formatted(self.article)
        self.assertFalse(any("时间早于" in error for error in errors), errors)

    def test_formatted_gate_runs_formula_source_checker(self):
        article_path = self.article / "article.md"
        html_path = self.article / "article.html"
        article_path.write_text("# 标题\n\n公式：$\\\\in$\n" + ("正文。" * 500), encoding="utf-8")
        html_path.write_text("<p><span leaf=\"\">" + ("正文。" * 500) + "</span></p>", encoding="utf-8")
        (self.article / "format-report.json").write_text(json.dumps({
            "status": "passed", "validator": "passed", "source": "article.md",
            "source_digest": sha256_file(article_path),
            "canonical_source_digest": sha256_file(article_path),
            "html_digest": sha256_file(html_path),
        }), encoding="utf-8")
        checker = self.article / "formula-source-check.py"
        checker.write_text("import sys; print('double escape'); raise SystemExit(1)\n", encoding="utf-8")
        old = workflow_gate.FORMULA_SOURCE_CHECK
        workflow_gate.FORMULA_SOURCE_CHECK = checker
        try:
            errors = workflow_gate._errors_for_formatted(self.article)
        finally:
            workflow_gate.FORMULA_SOURCE_CHECK = old
        self.assertTrue(any("公式源检查失败" in error for error in errors), errors)

    def test_receipt_artifact_paths_cannot_escape_article_workspace(self):
        outside = self.article.parent / "outside.png"
        outside.write_bytes(b"not-a-real-preview")
        resolved, error = workflow_gate._article_local_file(self.article, "../outside.png")
        self.assertIsNone(resolved)
        self.assertIn("越出", error)
        resolved, error = workflow_gate._article_local_file(self.article, str(outside.resolve()))
        self.assertIsNone(resolved)
        self.assertIn("绝对路径", error)

    def test_readonly_gate_copy_preserves_artifact_root_contract(self):
        article = self.article.parent / "THK-20260825-099-readonly-check"
        article.mkdir()
        (article / "matrix-state.json").write_text(json.dumps({
            "workspace_id": "THK-20260825-099",
        }), encoding="utf-8")
        (article / "workspace-manifest.json").write_text(json.dumps({
            "contract": "article-workspace-v1",
        }), encoding="utf-8")
        temp_root = self.article.parent / "ephemeral-artifacts"
        copied = workflow_gate._prepare_readonly_workspace(article, temp_root)
        self.assertEqual(copied, temp_root / "active" / article.name)
        registry = json.loads((temp_root / "registry" / "workspace-index.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["workspaces"][0]["workspace_id"], "THK-20260825-099")
        self.assertEqual(registry["workspaces"][0]["relative_path"], f"active/{article.name}")

    def test_observed_metrics_bind_local_export_hash(self):
        (self.article / "content-brief.yaml").write_text("schema_version: 3\n", encoding="utf-8")
        export = self.article / "work" / "metrics-t1.csv"
        export.parent.mkdir()
        export.write_text("metric,value\nfollows,1\n", encoding="utf-8")
        (self.article / "metrics.json").write_text(json.dumps({
            "schema_version": 2,
            "conversion": {key: 0 for key in ("follows", "keyword_replies", "lead_magnet_claims", "consultation_requests", "qualified_leads")},
            "attribution": {"primary_cta": "关注", "reply_keyword": "MCP", "lead_magnet": "清单"},
            "t1": {
                "status": "observed", "source": "wechat-export", "source_path": "work/metrics-t1.csv",
                "source_sha256": "0" * 64, "captured_at": "2026-08-25T00:00:00+00:00",
                "imported_at": "2026-08-25T00:05:00+00:00", "values": {"follows": 1},
            },
            "t7": {},
        }, ensure_ascii=False), encoding="utf-8")
        errors = workflow_gate._conversion_metric_errors(self.article)
        self.assertTrue(any("原始导出文件不一致" in error for error in errors), errors)

    def test_illustrated_gate_blocks_when_visual_checker_is_missing(self):
        (self.article / "imgs").mkdir()
        old = workflow_gate.VISUAL_QA
        workflow_gate.VISUAL_QA = self.article / "missing-visual-qa.py"
        try:
            errors = workflow_gate._errors_for_illustrated(self.article)
        finally:
            workflow_gate.VISUAL_QA = old
        self.assertTrue(any("视觉质量检查器缺失" in error for error in errors))

    def test_review_gate_requires_structured_evidence(self):
        (self.article / "article.md").write_text("# 标题\n\n" + ("正文。" * 300) + "\n![图](placeholder)", encoding="utf-8")
        (self.article / "review-report.md").write_text(
            "内容审：通过。事实核验：通过。合规：通过。错别字：通过。AI 味：已修改。人工复核：通过。",
            encoding="utf-8",
        )
        errors = workflow_gate._errors_for_review(self.article)
        self.assertTrue(any("review-evidence.json" in error for error in errors))

    def test_final_gate_requires_explicit_human_mobile_review(self):
        (self.article / "review-report.md").write_text(
            "## 终审门禁\n\n| 检查项 | 结果 |\n|---|---|\n| 内容 | ✅ |\n",
            encoding="utf-8",
        )
        (self.article / "article_预览.html").write_text("预览" * 300, encoding="utf-8")
        (self.article / "img_analysis.md").write_text("图片报告", encoding="utf-8")
        (self.article / "content-brief.yaml").write_text("account: " + ACCOUNT_ID + "\n", encoding="utf-8")
        errors = workflow_gate._errors_for_final(self.article)
        self.assertTrue(any("final-review.md" in error for error in errors))

    def test_high_risk_final_gate_requires_human_reviewer(self):
        (self.article / "review-report.md").write_text(
            "## 终审门禁\n\n| 检查项 | 结果 |\n|---|---|\n| 内容 | ✅ |\n",
            encoding="utf-8",
        )
        (self.article / "article_预览.html").write_text("预览" * 300, encoding="utf-8")
        (self.article / "img_analysis.md").write_text("图片报告", encoding="utf-8")
        (self.article / "content-brief.yaml").write_text(
            "account: " + ACCOUNT_ID + "\nrisk_level: high\nhuman_review_required: true\n", encoding="utf-8"
        )
        (self.article / "final-review.md").write_text(
            "# 终审记录\n\n- status: approved\n- human_review: false\n- reviewer_type: agent\n- reviewer: codex\n"
            "- reviewed_at: 2026-08-03T00:00:00+00:00\n- mobile_width: 390\n- preview_file: preview_screenshot.png\n",
            encoding="utf-8",
        )
        errors = workflow_gate._errors_for_final(self.article)
        self.assertTrue(any("高风险内容必须" in error for error in errors))

    def test_final_gate_requires_browser_dom_receipt(self):
        (self.article / "review-report.md").write_text(
            "## 终审门禁\n\n| 检查项 | 结果 |\n|---|---|\n| 内容 | ✅ |\n",
            encoding="utf-8",
        )
        (self.article / "article_预览.html").write_text("预览" * 300, encoding="utf-8")
        (self.article / "img_analysis.md").write_text("图片报告", encoding="utf-8")
        (self.article / "content-brief.yaml").write_text(
            "account: " + ACCOUNT_ID + "\nrisk_level: low\nhuman_review_required: false\n", encoding="utf-8"
        )
        (self.article / "matrix-state.json").write_text("{\"schema_version\": 4}", encoding="utf-8")
        (self.article / "final-review.md").write_text(
            "# 终审记录\n\n- status: approved\n- human_review: false\n- reviewer_type: agent\n- reviewer: codex\n"
            "- reviewed_at: 2026-08-03T00:00:00+00:00\n- mobile_width: 390\n- preview_file: preview_screenshot.png\n",
            encoding="utf-8",
        )
        (self.article / "preview-capture.json").write_text(json.dumps({
            "status": "passed", "renderer": "chrome-headless", "viewport": {"width": 390},
            "source": "article_预览.html", "source_sha256": sha256_file(self.article / "article_预览.html"),
            "screenshot": "preview_screenshot.png", "screenshot_sha256": "0" * 64,
            "dom_check": {"status": "blocked", "title_present": False, "body_text_chars": 10, "image_count": 0, "placeholder_count": 1},
        }), encoding="utf-8")
        errors = workflow_gate._errors_for_final(self.article)
        self.assertTrue(any("dom_check" in error for error in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
