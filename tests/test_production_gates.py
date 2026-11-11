#!/usr/bin/env python3
"""Regression tests for the stable production entry and its six gates.

Run standalone (no pytest): python tests/test_production_gates.py

All fixtures are throwaway temp directories. No provider, no network, no
render and no real project is touched.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import make_content  # noqa: E402
import production_gates as gates  # noqa: E402
import qc_video  # noqa: E402
from contentops.workflow import copy_review  # noqa: E402

INTENT_KW = {
    "account": "explorer",
    "asset_policy": "supplement",
    "avatar_intro": "no",
    "avatar_outro": "no",
    "avatar_quota_budget": None,
    "narration": "minimax-clone",
    "motion_backend": "huashu-art-motion",
    "reviewer": "Test Reviewer",
    "opinion": "gates answered for the regression fixture",
}


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "projects" / "demo"
        for folder in ("receipts", "sources", "script", "00_brief", "final"):
            (self.project / folder).mkdir(parents=True, exist_ok=True)
        (self.project / "project.yaml").write_text(
            "id: demo\ntitle: Demo\nstatus: initialized\n", encoding="utf-8")
        _write(self.project / "sources" / "assets.json", {"assets": [
            {"id": "shot_a", "sha256": "a" * 64, "type": "REAL_DOCUMENT",
             "repo_path": "sources/cards/a.png"}]})
        _write(self.project / "script" / "script.json", {"lines": [
            {"id": "l1", "narration": "one beat", "asset_id": "shot_a"}]})
        _write(self.project / "script" / "assets.json",
               {"schema": "contentops.m5-script-assets/v1", "assets": {}})
        _write(self.project / "script" / "claims.json",
               {"schema": "contentops.claim-ledger/v1", "claims": []})
        _write(self.project / "sources" / "source-refs.json",
               {"schema": "contentops.m5-source-refs/v1", "refs": []})
        _write(self.project / "00_brief" / "evidence-pack.json", {"items": [
            {"evidence_id": "E-1", "url": "https://example.org/doc",
             "sha256": "b" * 64, "excerpt": "verbatim source"}]})
        # Decision gates are tested independently of this host's credentials.
        self.env_patch = mock.patch.object(gates, "_env_has", return_value=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self._approve()

    def tearDown(self):
        self.tmp.cleanup()

    def _approve(self):
        copy_review.decide(
            self.project, status_value="APPROVED", reviewer="Test Reviewer",
            opinion="copy reviewed",
            reviewed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def _answer(self, **overrides):
        kw = {**INTENT_KW, **overrides}
        intent = gates.write_intent(self.project, **kw, root=ROOT)
        gates.apply_project_config(self.project, intent)
        return intent


class AccountTests(FixtureCase):
    def test_bundle_role_maps_to_verified_dna_slug(self):
        self.assertEqual(gates.resolve_account("explorer", ROOT), "x-superplay-1024")
        self.assertEqual(gates.resolve_account("thinktank", ROOT),
                         "x-superplay-future-intelligence")
        self.assertEqual(gates.resolve_account("x-superplay-1024", ROOT),
                         "x-superplay-1024")

    def test_unknown_account_fails_closed(self):
        with self.assertRaises(gates.GateError) as ctx:
            gates.resolve_account("not-an-account", ROOT)
        self.assertEqual(ctx.exception.code, "ACCOUNT_DNA_MISSING")


class IntentTests(FixtureCase):
    def test_check_blocks_without_intent(self):
        report = gates.check(self.project, root=ROOT)
        self.assertFalse(report["ok"])
        self.assertIn("intent", [row["gate"] for row in report["gates"]])

    def test_answer_writes_load_bearing_blocks(self):
        self._answer()
        intent = gates.load_intent(self.project)
        self.assertIsNotNone(intent)
        self.assertEqual(intent["account_slug"], "x-superplay-1024")
        text = (self.project / "project.yaml").read_text(encoding="utf-8")
        self.assertIn("account_slug: x-superplay-1024", text)
        self.assertIn("backend: huashu-art-motion", text)
        self.assertTrue((self.project / gates.BACKUP_FILE).is_file())

    def test_answer_is_idempotent(self):
        self._answer()
        first = (self.project / "project.yaml").read_text(encoding="utf-8")
        self._answer()
        self.assertEqual((self.project / "project.yaml").read_text(encoding="utf-8"), first)

    def test_conflicting_account_slug_refused(self):
        (self.project / "project.yaml").write_text(
            "id: demo\naccount_slug: x-superplay-future-intelligence\n", encoding="utf-8")
        with self.assertRaises(gates.GateError) as ctx:
            self._answer()
        self.assertEqual(ctx.exception.code, "ACCOUNT_CONFLICT")

    def test_all_gates_pass_on_a_complete_project(self):
        self._answer()
        report = gates.check(self.project, root=ROOT)
        failed = [row for row in report["gates"] if not row["ok"]]
        self.assertTrue(report["ok"], f"unexpected gate failures: {failed}")
        self.assertEqual({row["gate"] for row in report["gates"]}, set(gates.GATES))
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["publish_authorized"])


class IndividualGateTests(FixtureCase):
    def test_unapproved_copy_review_blocks(self):
        self._answer()
        (self.project / "receipts" / "script-review.json").unlink()
        report = gates.check(self.project, root=ROOT)
        gate = next(row for row in report["gates"] if row["gate"] == "copy_review")
        self.assertFalse(gate["ok"])
        self.assertFalse(report["ok"])

    def test_stale_copy_review_blocks(self):
        self._answer()
        _write(self.project / "script" / "script.json", {"lines": [
            {"id": "l1", "narration": "changed after approval", "asset_id": "shot_a"}]})
        report = gates.check(self.project, root=ROOT)
        gate = next(row for row in report["gates"] if row["gate"] == "copy_review")
        self.assertFalse(gate["ok"])

    def test_missing_evidence_link_blocks(self):
        self._answer()
        _write(self.project / "00_brief" / "evidence-pack.json", {"items": [
            {"evidence_id": "E-1", "sha256": "b" * 64}]})
        gate = next(row for row in gates.check(self.project, root=ROOT)["gates"]
                    if row["gate"] == "evidence_links")
        self.assertFalse(gate["ok"])

    def test_insufficient_assets_require_an_explicit_policy(self):
        intent = self._answer(asset_policy="supplement")
        _write(self.project / "script" / "script.json", {"lines": [
            {"id": "l1", "asset_id": "shot_a"}, {"id": "l2", "asset_id": "shot_b"}]})
        self._approve()
        report = gates.check(self.project, root=ROOT)
        gate = next(row for row in report["gates"] if row["gate"] == "asset_sufficiency")
        self.assertFalse(gate["ok"])
        self.assertIn("policy=supplement", gate["detail"])
        self.assertEqual(intent["asset_policy"], "supplement")

    def test_minimax_consent_is_refused_up_front_not_a_dead_end(self):
        # Recording an option that can never pass was the old dead end. The
        # answer step now refuses it and names both ways to make it real.
        with self.assertRaises(gates.GateError) as ctx:
            self._answer(asset_policy="minimax-authorized")
        self.assertEqual(ctx.exception.code, "MINIMAX_NOT_AVAILABLE")
        self.assertIn("ADR-014", ctx.exception.detail)

    def test_avatar_bookends_need_explicit_yes_no_and_quota(self):
        with self.assertRaises(gates.GateError) as ctx:
            gates.write_intent(self.project, **{**INTENT_KW, "avatar_intro": "",
                                                "avatar_outro": ""}, root=ROOT)
        self.assertEqual(ctx.exception.code, "AVATAR_DECISION_REQUIRED")
        with self.assertRaises(gates.GateError) as ctx:
            gates.write_intent(self.project, **{**INTENT_KW, "avatar_intro": "yes",
                                                "avatar_quota_budget": None}, root=ROOT)
        self.assertEqual(ctx.exception.code, "AVATAR_QUOTA_REQUIRED")

    def test_named_reviewer_and_opinion_are_mandatory(self):
        with self.assertRaises(gates.GateError) as ctx:
            gates.write_intent(self.project, **{**INTENT_KW, "reviewer": ""}, root=ROOT)
        self.assertEqual(ctx.exception.code, "REVIEWER_REQUIRED")


class EntrypointTests(FixtureCase):
    def test_run_refuses_producer_when_a_gate_is_open(self):
        args = SimpleNamespace(project=str(self.project), mode="STRICT", dry_run=False)
        with mock.patch("produce_video.produce") as producer, redirect_stdout(io.StringIO()):
            code = make_content.cmd_run(args)
        self.assertEqual(code, 4)
        producer.assert_not_called()

    def test_run_dry_run_passes_when_gates_are_closed(self):
        self._answer()
        args = SimpleNamespace(project=str(self.project), mode="STRICT", dry_run=True)
        with redirect_stdout(io.StringIO()) as stream:
            code = make_content.cmd_run(args)
        self.assertEqual(code, 0)
        self.assertIn("PREFLIGHT_PASS_DRY_RUN", stream.getvalue())

    def test_check_command_exit_code(self):
        args = SimpleNamespace(project=str(self.project))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(make_content.cmd_check(args), 4)
        self._answer()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(make_content.cmd_check(args), 0)


class RuntimeReadinessTests(FixtureCase):
    def test_missing_provider_keys_block_before_render(self):
        self._answer()
        with mock.patch.object(gates, "_env_has", return_value=False):
            report = gates.check(self.project, root=ROOT)
        gate = next(r for r in report["gates"] if r["gate"] == "runtime_readiness")
        self.assertFalse(gate["ok"])
        joined = " ".join(gate["problems"])
        self.assertIn("MINIMAX", joined)
        self.assertIn("SILICONFLOW", joined)
        self.assertFalse(report["ok"])

    def test_motion_without_source_refs_is_not_executable(self):
        self._answer()
        (self.project / "sources" / "source-refs.json").unlink()
        gate = next(r for r in gates.check(self.project, root=ROOT)["gates"]
                    if r["gate"] == "runtime_readiness")
        self.assertFalse(gate["ok"])
        self.assertTrue(any("source-refs.json" in p for p in gate["problems"]))

    def test_graphic_line_gets_its_own_gate_set(self):
        self._answer()
        (self.project / "script" / "script.json").unlink()
        _write(self.project / "graphic-input.json", {"title": "graphic", "images": []})
        report = gates.check(self.project, root=ROOT)
        self.assertFalse(report["ok"])
        self.assertEqual(report.get("format"), "GRAPHIC_TEXT")
        seen = [row["gate"] for row in report["gates"]]
        self.assertIn("asset_rights", seen)
        self.assertNotIn("format", seen)


class GraphicLineTests(FixtureCase):
    def setUp(self):
        super().setUp()
        (self.project / "script" / "script.json").unlink()
        (self.project / "script" / "claims.json").unlink()
        (self.project / "sources" / "assets.json").unlink()
        (self.project / "assets" / "images").mkdir(parents=True)
        (self.project / "assets" / "images" / "a.png").write_bytes(b"png")
        _write(self.project / "assets" / "a.rights.json",
               {"schema": "contentops.media-rights-review/v1",
                "license_id": "OWNED-BY-OPERATOR", "source_url": "OWNED",
                "reviewed_by": "Test", "reviewed_at": "2026-11-12"})
        (self.project / "draft.md").write_text(
            "# Draft\n\n[LoRA](https://arxiv.org/abs/2106.09685)\n"
            "[QLoRA](https://arxiv.org/abs/2305.14314)\n"
            "[Rules](https://github.com/Xander-Xai/X-SuperPlay-ContentOps)\n",
            encoding="utf-8")
        _write(self.project / "graphic-input.json", {
            "title": "Graphic", "platform_id": "wechat_article",
            "draft": "draft.md", "images": [{
                "asset_id": "a", "path": "assets/images/a.png", "alt": "alt text",
                "rights": {"license_id": "OWNED-BY-OPERATOR",
                           "source_url": "OWNED", "reviewed_by": "Test",
                           "reviewed_at": "2026-11-12",
                           "review_evidence": "assets/a.rights.json"}}]})
        self._approve()

    def test_graphic_all_gates_pass(self):
        self._answer()
        report = gates.check(self.project, root=ROOT)
        failed = [row for row in report["gates"] if not row["ok"]]
        self.assertTrue(report["ok"], f"unexpected: {failed}")
        self.assertEqual(report["format"], "GRAPHIC_TEXT")

    def test_graphic_copy_review_binds_to_the_draft(self):
        self._answer()
        (self.project / "draft.md").write_text("# Draft changed\n", encoding="utf-8")
        report = gates.check(self.project, root=ROOT)
        gate = next(row for row in report["gates"] if row["gate"] == "copy_review")
        self.assertFalse(gate["ok"])

    def test_graphic_needs_alt_and_rights(self):
        self._answer()
        _write(self.project / "graphic-input.json", {
            "title": "Graphic", "images": [{"asset_id": "a", "path": "assets/images/a.png"}]})
        report = gates.check(self.project, root=ROOT)
        gate = next(row for row in report["gates"] if row["gate"] == "asset_rights")
        self.assertFalse(gate["ok"])

    def test_run_routes_to_the_graphic_producer_not_m5(self):
        # The 2026-11-12 acceptance bug: five green graphic gates, then
        # produce_video blocked the run at M5's brief gate.
        self._answer()
        args = SimpleNamespace(project=str(self.project), mode="STRICT", dry_run=False)
        with mock.patch.object(
                make_content, "_produce_graphic",
                return_value={"state": "AWAITING_MANUAL_REVIEW",
                              "package": "receipts/graphic-package.json"}) as graphic, \
                mock.patch("produce_video.produce") as producer, \
                redirect_stdout(io.StringIO()):
            code = make_content.cmd_run(args)
        graphic.assert_called_once()
        producer.assert_not_called()
        self.assertEqual(code, 1)  # AWAITING_MANUAL_REVIEW, not QC_PASSED

    def test_produce_graphic_builds_the_manual_package(self):
        handoff = self.project / "receipts" / "bundle-handoff-graphic_text.json"
        _write(handoff, {"schema": "contentops.bundle-handoff/v1",
                         "bundle_id": "CB-TEST", "bundle_sha256": "0" * 64,
                         "bundle_path": "bundle.json", "bundle_scope": "repo",
                         "content_format": "GRAPHIC_TEXT",
                         "project_slug": self.project.name,
                         "state": "READY_FOR_MANUAL_PACKAGE", "blockers": [],
                         "production_ready": False, "publish_authorized": False})
        (self.project / "bundle.json").write_text("{}", encoding="utf-8")
        with mock.patch("contentops.graphic.build_package",
                        return_value={"status": "AWAITING_MANUAL_REVIEW"}) as build, \
                mock.patch("contentops.graphic.write_package") as write:
            result = make_content._produce_graphic(self.project, {})
        build.assert_called_once()
        write.assert_called_once()
        self.assertEqual(result["state"], "AWAITING_MANUAL_REVIEW")


class QcReceiptProtectionTests(FixtureCase):
    def _current_pass_receipt(self):
        _write(self.project / "receipts" / "qc-report-demo.json", {
            "schema": "contentops.qc-canonical/v1", "currency": "CURRENT",
            "overall": "PASS", "graded_target": "project://final/demo.mp4",
            "checks": [{"id": "file_size", "ok": True},
                       {"id": "resolution", "ok": True},
                       {"id": "audio_present", "ok": True}]})

    def test_bare_slug_refused_without_writing_a_receipt(self):
        self._current_pass_receipt()
        before = (self.project / "receipts" / "qc-report-demo.json").read_bytes()
        with redirect_stdout(io.StringIO()):
            result = qc_video.qc(self.project, target="demo")
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("QC_TARGET_INVALID", result["reason"])
        self.assertEqual((self.project / "receipts" / "qc-report-demo.json").read_bytes(),
                         before)

    def test_missing_render_cannot_overwrite_current_pass(self):
        self._current_pass_receipt()
        before = (self.project / "receipts" / "qc-report-demo.json").read_bytes()
        with redirect_stdout(io.StringIO()):
            result = qc_video.qc(self.project, target="demo.mp4")
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("QC_RECEIPT_PROTECTED", result["reason"])
        self.assertEqual((self.project / "receipts" / "qc-report-demo.json").read_bytes(),
                         before)

    def test_engine_name_resolves_to_mp4(self):
        self._current_pass_receipt()
        with mock.patch.object(qc_video, "_emit",
                               return_value={"state": "OK"}) as emit, \
                redirect_stdout(io.StringIO()):
            result = qc_video.qc(self.project, target="easel")
        self.assertNotIn("QC_TARGET_INVALID", result.get("reason", ""))
        graded_path = emit.call_args[0][1][0]["path"]
        self.assertTrue(graded_path.endswith("easel.mp4"), graded_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
