#!/usr/bin/env python3
"""Fast point-to-point negative checks for the revised adversarial report.

This suite deliberately avoids the expensive nine-gate visual fixture and
does not call WeChat. It checks the trust-boundary invariants directly so a
CI run can finish quickly.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "gzh-draft-publisher" / "scripts"))

import publish  # noqa: E402
from content_truth_qa import check as truth_check  # noqa: E402
from receipt_integrity import stamp, verify  # noqa: E402
from source_evidence import classify_source  # noqa: E402
from topic_integrity import check_alignment  # noqa: E402
from visual_reader_test import build_packet  # noqa: E402
from workflow_security import DuplicateKeyError, StateConflict, load_yaml_text  # noqa: E402
from workspace_hygiene import canonical_manifest_payload, manifest_errors, manifest_signature_errors  # noqa: E402
import workflow_gate  # noqa: E402


def _article(root: Path) -> Path:
    article = root / "article"
    article.mkdir()
    (article / "article.md").write_text("# Demo\n", encoding="utf-8")
    (article / "article.html").write_text("<p>Demo</p>", encoding="utf-8")
    return article


def prepare_topic(article: Path) -> None:
    """Create the minimal approved topic fixture used by the negative check.

    The standalone topic-integrity test module is optional QA and is not part
    of the production workflow. Keep this adversarial gate self-contained so
    removing optional test files cannot break the required regression check.
    """
    contract = {
        "schema_version": 1,
        "status": "approved",
        "canonical_topic": "vLLM",
        "topic_thesis": "vLLM 推理引擎的工程边界",
        "reader_problem": "读者需要知道如何部署 vLLM",
        "scope": {"in_scope": ["推理引擎", "部署"], "out_of_scope": ["无关教程"]},
        "anchor": {"required_terms": ["vLLM", "推理"], "aliases": ["vllm"], "minimum_total_hits": 3},
        "series": {
            "mode": "cluster",
            "subtopics": [
                {"id": "cache", "title": "KV Cache", "relation": "supporting", "why_it_belongs": "解释 vLLM 的支持机制", "return_to_topic": "回到 vLLM 的推理路径"},
                {"id": "batch", "title": "Continuous Batching", "relation": "core", "why_it_belongs": "解释 vLLM 的核心能力", "return_to_topic": "回到 vLLM 的吞吐优化"},
                {"id": "deploy", "title": "部署", "relation": "adjacent", "why_it_belongs": "说明 vLLM 的上线边界", "return_to_topic": "回到 vLLM 的部署决策"},
            ],
        },
        "drift_rules": {
            "min_anchor_coverage": 0.6,
            "max_anchorless_sections": 1,
            "require_anchor_in_title": True,
            "require_anchor_in_lead": True,
            "require_section_return": True,
        },
        "approval": {"reviewer": "test", "approved_at": "2026-08-13T00:00:00+08:00"},
    }
    (article / "topic-contract.yaml").write_text(json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    (article / "article.yaml").write_text(json.dumps({"title": "vLLM 推理引擎"}, ensure_ascii=False), encoding="utf-8")
    (article / "content-brief.yaml").write_text(json.dumps({"title": "vLLM 推理引擎", "primary_keyword": "vLLM"}, ensure_ascii=False), encoding="utf-8")
    (article / "topic-cluster.md").write_text("# vLLM\n\n推理引擎主题回链。\n", encoding="utf-8")
    (article / "article.md").write_text("# vLLM 推理引擎\n\nvLLM 推理主题。\n", encoding="utf-8")


def test_r00_production_raw_key_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r00-") as raw:
        article = _article(Path(raw))
        old_mode = os.environ.pop("WORKFLOW_TEST_MODE", None)
        old_key = os.environ.get("WORKFLOW_RECEIPT_SIGNING_KEY")
        try:
            os.environ["WORKFLOW_RECEIPT_SIGNING_KEY"] = "attacker-controlled-key-with-32-bytes-plus"
            doc = stamp({"target_kind": "wechat"}, article, receipt_kind="publish-receipt", account_slot=workflow_gate.PUBLISH_SLOT)
            assert doc["signature_status"] != "signed"
            assert any("禁止使用 WORKFLOW_RECEIPT_SIGNING_KEY" in item for item in verify(doc, article, receipt_kind="publish-receipt", account_slot=workflow_gate.PUBLISH_SLOT))
        finally:
            os.environ.pop("WORKFLOW_RECEIPT_SIGNING_KEY", None)
            if old_key is not None:
                os.environ["WORKFLOW_RECEIPT_SIGNING_KEY"] = old_key
            if old_mode is not None:
                os.environ["WORKFLOW_TEST_MODE"] = old_mode


def test_r00b_external_production_key_round_trip() -> None:
    """The replacement trust root must work without putting a secret in-repo."""
    with tempfile.TemporaryDirectory(prefix="adv-v2-r00b-") as raw, tempfile.TemporaryDirectory(prefix="adv-v2-r00b-key-") as ext:
        article = _article(Path(raw))
        key_path = Path(ext) / "receipt.key"
        key_path.write_bytes(b"external-production-key-v1-32-bytes!!")
        old_mode = os.environ.pop("WORKFLOW_TEST_MODE", None)
        old_raw = os.environ.pop("WORKFLOW_RECEIPT_SIGNING_KEY", None)
        old_path = os.environ.get("WORKFLOW_RECEIPT_SIGNING_KEY_PATH")
        os.environ["WORKFLOW_RECEIPT_SIGNING_KEY_PATH"] = str(key_path)
        try:
            document = stamp({"target_kind": "wechat"}, article, receipt_kind="publish-receipt", account_slot=workflow_gate.PUBLISH_SLOT)
            assert document["signature_status"] == "signed"
            assert document["issuer"] == "external-signer"
            assert verify(document, article, receipt_kind="publish-receipt", account_slot=workflow_gate.PUBLISH_SLOT) == []
        finally:
            os.environ.pop("WORKFLOW_RECEIPT_SIGNING_KEY_PATH", None)
            if old_path is not None:
                os.environ["WORKFLOW_RECEIPT_SIGNING_KEY_PATH"] = old_path
            if old_raw is not None:
                os.environ["WORKFLOW_RECEIPT_SIGNING_KEY"] = old_raw
            if old_mode is not None:
                os.environ["WORKFLOW_TEST_MODE"] = old_mode


def test_r01_test_namespace_cannot_be_wechat() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r01-") as raw:
        article = _article(Path(raw))
        old = os.environ.get("WORKFLOW_TEST_MODE")
        os.environ["WORKFLOW_TEST_MODE"] = "1"
        try:
            doc = stamp({"target_kind": "wechat"}, article, receipt_kind="publish-receipt", account_slot=workflow_gate.PUBLISH_SLOT)
            assert any("禁止声明 target_kind=wechat" in item for item in verify(doc, article, receipt_kind="publish-receipt", account_slot=workflow_gate.PUBLISH_SLOT))
        finally:
            if old is None:
                os.environ.pop("WORKFLOW_TEST_MODE", None)
            else:
                os.environ["WORKFLOW_TEST_MODE"] = old


def test_r02_matrix_init_rejects_legacy_drafts_root() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r02-") as raw:
        artifact_root = Path(raw) / "artifact-root"
        route = artifact_root / "registry" / "routes" / "route.yaml"
        route.parent.mkdir(parents=True, exist_ok=True)
        route.write_text(json.dumps({
            "schema_version": 1,
            "status": "confirmed",
            "content_medium": "wechat_article",
            "sequence": ["topic_route", "account_route"],
            "topic_route": {"mode": "hotspot", "topic": "边界", "reference": "", "selected_skill": "gzh-topic-research", "routed_at": "2026-08-13T00:00:00+00:00"},
            "account_route": {"account": "thinktank", "display_name": "X超玩•未来智能", "routed_at": "2026-08-13T00:00:00+00:00"},
            "operator": "test", "confirmed_at": "2026-08-13T00:00:00+00:00",
        }, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env["GZH_ARTIFACT_ROOT"] = str(artifact_root)
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "matrix_init.py"), "--title", "边界", "--root", "drafts", "--route", str(route)],
            cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert result.returncode != 0 and "drafts" in (result.stdout + result.stderr)


def test_r03_reader_answers_without_approval_blocked() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r03-") as raw:
        article = _article(Path(raw))
        (article / "visual-contract.json").write_text(json.dumps({"units": [{"id": "body-01", "reader_question": "What?", "answer_sentence": "x"}]}), encoding="utf-8")
        answers = Path(raw) / "answers.json"
        answers.write_text(json.dumps({"responses": [{"question_id": "q-01", "unit_id": "body-01", "correct": True, "score": 4, "answer": "x"}]}), encoding="utf-8")
        packet = build_packet(article, answers, "reviewer")
        assert packet["status"] == "blocked"


def test_r04_official_label_cannot_trust_evil_host() -> None:
    tier, trusted, reason = classify_source({"url": "https://evil.example/fake", "evidence_level": "official-docs", "official_source": "official"})
    assert (tier, trusted) == ("untrusted", False), reason


def test_r05_hidden_topic_anchor_blocked() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r05-") as raw:
        article = Path(raw)
        prepare_topic(article)
        (article / "article.md").write_text("# vLLM 推理引擎\n\n<!-- vLLM 推理引擎 vLLM -->\n## 旅行\n\n只讨论旅行。\n", encoding="utf-8")
        assert check_alignment(article), "隐藏注释不应让无关正文通过主题检查"


def test_r06_claim_ledger_phrase_without_binding_blocked() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r06-") as raw:
        article = _article(Path(raw))
        (article / "article.md").write_text("# Demo\n\n这个方案是最靠谱。\n", encoding="utf-8")
        (article / "sources.json").write_text(json.dumps({"claims": [{"statement": "最靠谱"}]}), encoding="utf-8")
        result = truth_check(article)
        assert result["status"] == "blocked" and any("结构化 claim" in item for item in result["errors"])


def test_r07_duplicate_yaml_key_rejected() -> None:
    try:
        load_yaml_text("risk_level: critical\nrisk_level: low\n")
    except DuplicateKeyError:
        return
    raise AssertionError("duplicate YAML keys must fail closed")


def test_r08_manifest_requires_external_signature_when_requested() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r08-") as raw, tempfile.TemporaryDirectory(prefix="adv-v2-r08-ext-") as ext:
        root, outside = Path(raw), Path(ext)
        (root / "marker.txt").write_text("marker", encoding="utf-8")
        payload = {"schema_version": 3, "workflow": "thinktank", "files": [{"path": "marker.txt", "size": 6, "sha256": hashlib.sha256(b"marker").hexdigest()}]}
        payload["manifest_sha256"] = hashlib.sha256(canonical_manifest_payload(payload)).hexdigest()
        (root / "split-manifest.json").write_text(json.dumps(payload), encoding="utf-8")
        key = outside / "manifest.key"
        key.write_bytes(b"m" * 32)
        sig = outside / "manifest.sig.json"
        sig.write_text(json.dumps({"contract": "split-manifest-signature-v1", "manifest_sha256": payload["manifest_sha256"], "signature": hmac.new(key.read_bytes(), canonical_manifest_payload(payload), hashlib.sha256).hexdigest()}), encoding="utf-8")
        old_sig, old_key = os.environ.get("WORKFLOW_MANIFEST_SIGNATURE_PATH"), os.environ.get("WORKFLOW_MANIFEST_SIGNATURE_KEY_PATH")
        try:
            os.environ["WORKFLOW_MANIFEST_SIGNATURE_PATH"] = str(sig)
            os.environ["WORKFLOW_MANIFEST_SIGNATURE_KEY_PATH"] = str(key)
            assert manifest_errors(root) == []
            assert manifest_signature_errors(root, required=True) == []
        finally:
            if old_sig is None: os.environ.pop("WORKFLOW_MANIFEST_SIGNATURE_PATH", None)
            else: os.environ["WORKFLOW_MANIFEST_SIGNATURE_PATH"] = old_sig
            if old_key is None: os.environ.pop("WORKFLOW_MANIFEST_SIGNATURE_KEY_PATH", None)
            else: os.environ["WORKFLOW_MANIFEST_SIGNATURE_KEY_PATH"] = old_key


def test_r09_external_publish_requires_approval() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r09-") as raw:
        article = _article(Path(raw))
        (article / "publish-attempt.json").write_text(json.dumps({"media_id": "m"}), encoding="utf-8")
        with mock.patch.object(publish, "ensure_article_path", return_value=article):
            errors = publish._external_publish_guard(article, "m")
        assert any("external_publish" in item for item in errors)


def test_r09b_full_publish_never_calls_freepublish_inline() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r09b-") as raw:
        article = _article(Path(raw))
        (article / "article.yaml").write_text("title: Demo\nauthor: Tester\ndigest: Demo\n", encoding="utf-8")
        (article / "cover.png").write_bytes(b"cover")
        old_mode = os.environ.pop("WORKFLOW_TEST_MODE", None)
        try:
            with mock.patch.object(publish, "_article_publish_guard", return_value=[]), \
                 mock.patch.object(publish, "_run_publish_gate", return_value=[]), \
                 mock.patch.object(publish, "upload_thumb", return_value={"media_id": "thumb", "url": ""}), \
                 mock.patch.object(publish, "create_draft", return_value="media"), \
                 mock.patch.object(publish, "publish_draft") as submit:
                try:
                    publish.full_publish("token", str(article), do_publish=True, account_slot=workflow_gate.PUBLISH_SLOT)
                except SystemExit:
                    pass
                assert not submit.called, "full --publish must stop before freepublish"
        finally:
            if old_mode is not None:
                os.environ["WORKFLOW_TEST_MODE"] = old_mode


def test_r10_attempt_requires_signed_readback() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r10-") as raw:
        article = _article(Path(raw))
        (article / "publish-attempt.json").write_text(json.dumps({"status": "draft_created", "media_id": "other", "account_slot": workflow_gate.PUBLISH_SLOT}), encoding="utf-8")
        with mock.patch.object(publish, "ensure_article_path", return_value=article):
            publish._draft_wechat_slot = workflow_gate.PUBLISH_SLOT
            try:
                errors = publish._article_attempt_guard(article, "other")
            finally:
                publish._draft_wechat_slot = None
        assert any("status=passed" in item or "完整性" in item for item in errors)


def test_r11_upload_requires_article_asset_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r11-") as raw:
        article = _article(Path(raw))
        arbitrary = Path(raw) / "outside.png"
        arbitrary.write_bytes(b"x")
        with mock.patch.object(publish, "ensure_article_path", return_value=article):
            errors = publish._asset_upload_guard(article, str(arbitrary))
        assert any("当前文章目录" in item for item in errors)


def test_r12_state_compare_and_swap_rejects_stale_writer() -> None:
    with tempfile.TemporaryDirectory(prefix="adv-v2-r12-") as raw:
        article = _article(Path(raw))
        state = article / "matrix-state.json"
        state.write_text(json.dumps({"current_stage": "none"}), encoding="utf-8")
        try:
            workflow_gate.save_state(article, {"current_stage": "environment_ready"}, expected_state_sha256="0" * 64)
        except StateConflict:
            return
    raise AssertionError("stale matrix-state writer must be rejected")


def main() -> int:
    tests = [value for name, value in globals().items() if name.startswith("test_r") and callable(value)]
    for test in sorted(tests, key=lambda fn: fn.__name__):
        test()
        print(f"[PASS] {test.__name__}")
    print(f"ADVERSARIAL CONTROL TESTS V2 PASSED: {len(tests)} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
