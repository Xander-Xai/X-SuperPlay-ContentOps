#!/usr/bin/env python3
"""Regression tests for the stable production entry and its fail-closed gates.

Run standalone (no pytest): python tests/test_production_gates.py

All fixtures are throwaway temp directories. No provider, no network, no
render and no real project is touched.
"""

from __future__ import annotations

import hashlib
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
from contentops.workflow import canonical_copy, copy_review, preresearch  # noqa: E402

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


def _seed_intent(project: Path) -> dict:
    """The router-shaped intent this fixture's research is done against."""
    intent = {
        "schema": preresearch.INTENT_SCHEMA,
        "account_id": "x-superplay-1024",
        "account_profile_version": "acc-x-superplay-1024@v3",
        "route_mode": "USER_TOPIC",
        "topic": "Regression fixture topic",
        "evidence_status": "verification_required",
        "approval_status": "pending",
        "target_pipeline": "VIDEO",
        "brief_status": "draft",
        "route_context": {"mode": "USER_TOPIC", "topic_origin": "USER_INPUT"},
        "created_at": "2026-11-12T09:00:00Z",
    }
    folder = project / preresearch.RESEARCH_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "content-intent.json").write_text(
        json.dumps(intent, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return intent


def _seed_preresearch(project: Path) -> None:
    """Give a fixture a signed, current pre-copy research package."""
    _seed_intent(project)
    folder = project / preresearch.RESEARCH_DIR
    (folder / "project-reading.md").write_text(
        "# Project read-through\n\n## Files read\n\n"
        "- `docs/RUNBOOK.md` records the stable entry commands and QC.\n"
        "- `scripts/make_content.py` records the gate decisions.\n"
        "- `docs/CONTENT-LIFECYCLE-STAGES.md` records the two production lines.\n\n"
        "## Findings\n\n"
        "- The stable entry is gated and never publishes.\n"
        "- A green QC is not production approval.\n", encoding="utf-8")
    (folder / "outline.md").write_text(
        "# Outline\n\n## Topic\n\n- Fixture outline for the regression run.\n\n"
        "## Video\n\n- One shot with a source citation.\n\n"
        "## Graphic\n\n- One draft with three links.\n\n"
        "## Boundary\n\n- Research only.\n", encoding="utf-8")
    _write(folder / "evidence-list.json", {
        "schema": "contentops.precopy-research-evidence/v1",
        "items": [
            {"id": "S1", "kind": "primary", "title": "LoRA paper",
             "url": "https://arxiv.org/abs/2106.09685"},
            {"id": "S2", "kind": "primary", "title": "QLoRA paper",
             "url": "https://arxiv.org/abs/2305.14314"},
            {"id": "S3", "kind": "official", "title": "Runbook",
             "url": "repo://docs/RUNBOOK.md"},
        ]})
    (folder / "boundary.md").write_text(
        "# Boundary\n\nThis phase does not render or publish.\n"
        "- `production_ready: false`\n- `publish_authorized: false`\n"
        "- Research approval is not copy approval.\n", encoding="utf-8")
    preresearch.approve(project, reviewer="Test Reviewer",
                        opinion="fixture research reviewed")


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
        # Host-runtime probes are environment-dependent: CI has neither the
        # Huashu motion runtime nor the gzh-design validator, so the same gate
        # logic must not depend on this host's install state. Stub only the
        # probes; the gate logic itself stays real. The probes are truth-tested
        # directly in HostProbeTests.
        for probe in ("_motion_runtime_present", "_graphic_validator_present"):
            patch = mock.patch.object(gates, probe, return_value=True)
            patch.start()
            self.addCleanup(patch.stop)
        _seed_preresearch(self.project)
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

    def test_canonical_copy_workflow_blocks_missing_format_derivative(self):
        self._answer()
        intent_path = self.project / preresearch.INTENT_FILE
        intent_raw = intent_path.read_bytes()
        canonical = {
            "schema": canonical_copy.SCHEMA,
            "copy_id": "copy-001",
            "intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "research_sha256": preresearch.check(self.project)["artifacts_sha256"],
            "account": "x-superplay-1024",
            "topic": "Regression fixture topic",
            "segments": [{"id": "s1", "text": "A sourced statement.",
                          "claim_refs": ["C1"]}],
            "claims": {"C1": {"statement": "A sourced statement.",
                                "evidence_refs": ["S1"]}},
        }
        _write(self.project / canonical_copy.CANONICAL_FILE, canonical)
        report = gates.check(self.project, root=ROOT)
        gate = next(row for row in report["gates"]
                    if row["gate"] == "shared_copy_lineage")
        self.assertFalse(gate["ok"])
        self.assertIn("DERIVATIVE_MISSING", gate["detail"])

    def test_missing_evidence_link_blocks(self):
        self._answer()
        _write(self.project / "00_brief" / "evidence-pack.json", {"items": [
            {"evidence_id": "E-1", "sha256": "b" * 64}]})
        gate = next(row for row in gates.check(self.project, root=ROOT)["gates"]
                    if row["gate"] == "evidence_links")
        self.assertFalse(gate["ok"])

    def test_verified_claim_ledger_supplies_links_without_editing_master_copy(self):
        self._answer()
        _write(self.project / "00_brief" / "evidence-pack.json", {
            "schema": "contentops.evidence-pack/v1",
            "items": [{"evidence_id": "E-1", "url": "https://example.org/source",
                       "sha256": "b" * 64, "excerpt": "pinned quote"}],
        })
        _write(self.project / "sources" / "source-refs.json", {
            "schema": "contentops.m5-source-refs/v1",
            "refs": [{"id": "E-1", "title": "Pinned source",
                      "url": "https://example.org/source", "path": "sources/e1.md",
                      "sha256": "b" * 64, "permission": "LICENSED"}],
        })
        _write(self.project / "script" / "claims.json", {
            "schema": "contentops.claim-ledger/v1",
            "claims": [{"id": "C1", "text": "A sourced statement.",
                        "artifacts": ["E-1"], "quotes": ["A pinned quote"]}],
        })
        _write(self.project / "script" / "master.md", "Creator's exact copy, without inline citations.\n")
        result = gates.evidence_links(self.project)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["links"], 0)
        self.assertEqual(result["claims"], 1)

    def test_asset_sufficiency_blocks_when_script_is_missing(self):
        self._answer()
        (self.project / "script" / "script.json").unlink()
        result = gates.asset_sufficiency(self.project)
        self.assertFalse(result["ok"], result)
        self.assertIn("script/script.json", result["detail"])

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


class HostProbeTests(unittest.TestCase):
    """The host-runtime probes must report absence truthfully.

    These are the seams every other test stubs out; testing them here keeps the
    "gate logic is hermetic, probes are environment checks" contract honest.
    """

    def test_motion_probe_is_false_when_discovery_raises(self):
        import types

        fake = types.ModuleType("contentops.media.huashu_runtime")

        def _raise(root=None):
            raise RuntimeError("runtime absent")

        fake.find_runtime = _raise
        with mock.patch.dict(sys.modules, {"contentops.media.huashu_runtime": fake}):
            self.assertFalse(gates._motion_runtime_present(ROOT))

    def test_graphic_validator_probe_tracks_file_presence(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertFalse(gates._graphic_validator_present(root))
            validator = (root / ".runtime" / "easel" / "skills" / "openclaw"
                         / "gzh-design" / "scripts" / "validate_gzh_html.py")
            validator.parent.mkdir(parents=True, exist_ok=True)
            validator.write_text("# stub validator\n", encoding="utf-8")
            self.assertTrue(gates._graphic_validator_present(root))


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
        _write(self.project / "receipts" / "bundle-handoff-graphic_text.json", {
            "schema": "contentops.bundle-handoff/v1",
            "content_format": "GRAPHIC_TEXT", "account": "explorer"})
        self._approve()

    def test_graphic_handoff_account_must_match_intent(self):
        intent = self._answer()
        handoff = self.project / "receipts" / "bundle-handoff-graphic_text.json"
        _write(handoff, {"schema": "contentops.bundle-handoff/v1",
                         "content_format": "GRAPHIC_TEXT", "account": "thinktank"})
        report = gates.check(self.project, root=ROOT, intent=intent)
        gate = next(row for row in report["gates"] if row["gate"] == "account")
        self.assertFalse(gate["ok"])
        self.assertIn("HANDOFF_ACCOUNT_MISMATCH", gate["detail"])

    def test_graphic_project_account_must_match_intent(self):
        intent = self._answer()
        (self.project / "project.yaml").write_text(
            "id: demo\\naccount_slug: x-superplay-future-intelligence\\n",
            encoding="utf-8")
        report = gates.check(self.project, root=ROOT, intent=intent)
        gate = next(row for row in report["gates"] if row["gate"] == "account")
        self.assertFalse(gate["ok"])
        self.assertIn("PROJECT_ACCOUNT_MISMATCH", gate["detail"])

    def test_graphic_all_gates_pass(self):
        self._answer()
        report = gates.check(self.project, root=ROOT)
        failed = [row for row in report["gates"] if not row["ok"]]
        self.assertTrue(report["ok"], f"unexpected: {failed}")
        self.assertEqual(report["format"], "GRAPHIC_TEXT")

    def test_graphic_needs_one_source_link_not_three(self):
        self._answer()
        (self.project / "draft.md").write_text(
            "# Draft\\n\\n[Primary source](https://example.org/source)\\n",
            encoding="utf-8")

        report = gates.check(self.project, root=ROOT)
        self.assertTrue(report["ok"], report)
        evidence = next(row for row in report["gates"]
                        if row["gate"] == "evidence_links")
        self.assertTrue(evidence["ok"], evidence)

    def test_graphic_preflight_does_not_require_copy_or_research_signoff(self):
        self._answer()
        (self.project / "receipts" / "script-review.json").unlink()
        (self.project / preresearch.RESEARCH_DIR / "boundary.md").write_text(
            "changed after the old approval", encoding="utf-8")

        report = gates.check(self.project, root=ROOT)

        failed = [row for row in report["gates"] if not row["ok"]]
        seen = {row["gate"] for row in report["gates"]}
        self.assertTrue(report["ok"], f"unexpected: {failed}")
        self.assertNotIn("copy_review", seen)
        self.assertNotIn("precopy_research", seen)

    def test_graphic_answer_needs_only_account_not_video_decisions(self):
        args = SimpleNamespace(
            interactive=False, account=None, asset_policy=None, avatar_intro=None,
            avatar_outro=None, narration=None, motion=None, bgm=None,
            reviewer=None, opinion=None, avatar_quota_budget=None,
        )

        answers = make_content._answers_from_args(args, self.project)
        intent = gates.write_intent(self.project, **answers, root=ROOT)

        self.assertEqual(answers["account"], "explorer")
        self.assertEqual(intent["answered_by"], None)
        self.assertEqual(intent["opinion"], None)
        self.assertEqual(intent["motion_backend"], "none")

    def test_graphic_copy_derivative_uses_the_canonical_source(self):
        self._answer()
        intent_path = self.project / preresearch.INTENT_FILE
        canonical = {
            "schema": canonical_copy.SCHEMA,
            "copy_id": "copy-graphic-001",
            "intent_sha256": hashlib.sha256(intent_path.read_bytes()).hexdigest(),
            "research_sha256": preresearch.check(self.project)["artifacts_sha256"],
            "account": "x-superplay-1024",
            "topic": "Regression fixture topic",
            "segments": [{"id": "s1", "text": "Canonical statement.",
                          "claim_refs": ["C1"]}],
            "claims": {"C1": {"statement": "Canonical statement.",
                                "evidence_refs": ["S1"]}},
        }
        derivative = {
            "schema": canonical_copy.DERIVATIVE_SCHEMA,
            "copy_id": canonical["copy_id"],
            "copy_sha256": canonical_copy.digest(canonical),
            "format": "GRAPHIC_TEXT",
            "segments": [{"source_segment_id": "s1",
                          "text": "Adapted article statement.",
                          "claim_refs": ["C1"]}],
        }
        _write(self.project / canonical_copy.CANONICAL_FILE, canonical)
        _write(self.project / canonical_copy.DERIVATIVE_FILE, derivative)
        with (self.project / "draft.md").open("a", encoding="utf-8") as draft:
            draft.write("\nAdapted article statement.\n")
        self._approve()
        report = gates.check(self.project, root=ROOT)
        gate = next(row for row in report["gates"]
                    if row["gate"] == "shared_copy_lineage")
        self.assertTrue(gate["ok"], gate)

    def test_graphic_copy_review_is_not_a_preflight_gate(self):
        self._answer()
        (self.project / "draft.md").write_text(
            "# Draft changed\n\n[LoRA](https://arxiv.org/abs/2106.09685)\n"
            "[QLoRA](https://arxiv.org/abs/2305.14314)\n"
            "[Rules](https://github.com/Xander-Xai/X-SuperPlay-ContentOps)\n",
            encoding="utf-8")
        report = gates.check(self.project, root=ROOT)
        self.assertTrue(report["ok"], report)
        self.assertNotIn("copy_review", {row["gate"] for row in report["gates"]})

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
        self.assertEqual(code, 0)  # package created; manual review is still pending

    def test_graphic_article_validation_failure_is_nonzero(self):
        self._answer()
        args = SimpleNamespace(project=str(self.project), mode="STRICT", dry_run=False)
        result = {"state": "AWAITING_MANUAL_REVIEW",
                  "package": "receipts/graphic-package.json",
                  "article": "BLOCKED: VALIDATION_FAILED"}
        with mock.patch.object(make_content, "_produce_graphic", return_value=result), \
                redirect_stdout(io.StringIO()):
            code = make_content.cmd_run(args)
        self.assertEqual(code, 1)

    def test_produce_graphic_builds_the_manual_package(self):
        handoff = self.project / "receipts" / "bundle-handoff-graphic_text.json"
        _write(handoff, {"schema": "contentops.bundle-handoff/v1",
                         "bundle_id": "CB-TEST", "bundle_sha256": "0" * 64,
                         "bundle_path": "bundle.json", "bundle_scope": "repo",
                         "content_format": "GRAPHIC_TEXT", "account": "explorer",
                         "project_slug": self.project.name,
                         "state": "READY_FOR_MANUAL_PACKAGE", "blockers": [],
                         "production_ready": False, "publish_authorized": False})
        (self.project / "bundle.json").write_text("{}", encoding="utf-8")
        intent = self._answer()
        with mock.patch("contentops.graphic.build_package",
                        return_value={"status": "AWAITING_MANUAL_REVIEW",
                                      "account": "explorer"}) as build, \
                mock.patch("contentops.graphic.write_package") as write:
            result = make_content._produce_graphic(self.project, intent)
        build.assert_called_once()
        write.assert_called_once()
        self.assertEqual(result["state"], "AWAITING_MANUAL_REVIEW")

    def test_produce_graphic_refuses_package_account_drift(self):
        handoff = self.project / "receipts" / "bundle-handoff-graphic_text.json"
        _write(handoff, {"schema": "contentops.bundle-handoff/v1",
                         "content_format": "GRAPHIC_TEXT", "account": "explorer"})
        (self.project / "bundle.json").write_text("{}", encoding="utf-8")
        intent = self._answer()
        with mock.patch("contentops.graphic.build_package",
                        return_value={"status": "AWAITING_MANUAL_REVIEW",
                                      "account": "thinktank"}), \
                mock.patch("contentops.graphic.write_package") as write:
            with self.assertRaises(gates.GateError) as ctx:
                make_content._produce_graphic(self.project, intent)
        self.assertEqual(ctx.exception.code, "GRAPHIC_PACKAGE_ACCOUNT_MISMATCH")
        write.assert_not_called()

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
