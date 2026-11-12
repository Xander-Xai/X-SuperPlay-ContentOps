#!/usr/bin/env python3
"""Pre-copy research gate: scaffold, check, sign, drift, and CLI wiring.

Run standalone (no pytest): python tests/test_precopy_research.py

All fixtures are throwaway temp directories. No provider, no network, no
render and no real project is touched.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.workflow import preresearch  # noqa: E402
import production_gates as gates  # noqa: E402


def _write_text(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _intent(route_mode: str = "USER_TOPIC", **overrides) -> dict:
    """A router-shaped ContentIntent. Deliberately the same shape in both modes."""
    context = {
        "mode": route_mode,
        "topic_origin": "USER_INPUT" if route_mode == "USER_TOPIC" else "HOTSPOT_SELECTION",
    }
    if route_mode == "HOTSPOT_DISCOVERY":
        context.update({"candidate_id": "CAND-TEST01", "search_plan_id": "PLAN-TEST01"})
    context.update(overrides.pop("route_context", {}))
    payload = {
        "schema": preresearch.INTENT_SCHEMA,
        "account_id": "x-superplay-1024",
        "account_profile_version": "acc-x-superplay-1024@v3",
        "route_mode": route_mode,
        "topic": "SFT / LoRA / QLoRA 到底怎么串起来",
        "content_angle": None,
        "source_artifact_refs": [],
        "evidence_status": "verification_required",
        "approval_status": "pending",
        "target_pipeline": "VIDEO",
        "brief_status": "draft",
        "route_context": context,
        "profile": {},
        "evidence": [],
        "profile_alignment": {},
        "created_at": "2026-11-12T09:00:00Z",
    }
    payload.update(overrides)
    return payload


def _brief(intent: dict) -> str:
    """The router brief package, as `contentops.routing.brief` writes it."""
    return json.dumps({"schema": preresearch.BRIEF_SCHEMA, "intent": intent,
                       "route": intent.get("route_context")},
                      ensure_ascii=False, indent=2)


def _valid_artifacts(project: Path, intent: dict = None) -> None:
    """Five artifacts that pass the content checks but are not yet approved."""
    folder = project / preresearch.RESEARCH_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "content-intent.json").write_text(
        json.dumps(intent if intent is not None else _intent(),
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    _write_text(folder / "project-reading.md",
                "# Project read-through\n\n## Files read\n\n"
                "- `docs/RUNBOOK.md` records the stable entry commands.\n"
                "- `scripts/make_content.py` records the gate decisions.\n"
                "- `docs/CONTENT-LIFECYCLE-STAGES.md` defines both lines.\n\n"
                "## Findings\n\n- The stable entry is gated and never publishes.\n"
                "- QC PASS is not production approval.\n")
    _write_text(folder / "outline.md",
                "# Outline\n\n## Topic\n\n- Research gate regression fixture.\n\n"
                "## Video\n\n- One shot with a citation.\n\n"
                "## Graphic\n\n- One draft with three links.\n\n"
                "## Evidence\n\n- Three authoritative sources.\n")
    (folder / "evidence-list.json").write_text(json.dumps({
        "schema": "contentops.precopy-research-evidence/v1",
        "items": [
            {"id": "S1", "kind": "primary", "title": "LoRA paper",
             "url": "https://arxiv.org/abs/2106.09685"},
            {"id": "S2", "kind": "primary", "title": "QLoRA paper",
             "url": "https://arxiv.org/abs/2305.14314"},
            {"id": "S3", "kind": "official", "title": "Runbook",
             "url": "repo://docs/RUNBOOK.md"},
        ]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_text(folder / "boundary.md",
                "# Boundary\n\nThis phase does not render or publish.\n"
                "- `production_ready: false`\n"
                "- `publish_authorized: false`\n"
                "- Research approval is not copy approval.\n")


def _preresearch_cli():
    path = ROOT / "scripts" / "preresearch.py"
    spec = importlib.util.spec_from_file_location("preresearch_cli", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load CLI from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResearchGateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "projects" / "demo"
        (self.project / "receipts").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_artifacts_block(self):
        report = preresearch.check(self.project)
        self.assertFalse(report["ok"])
        self.assertEqual(report["state"], "NOT_STARTED")
        self.assertEqual(len(report["missing"]), 5)
        with self.assertRaises(preresearch.PreresearchError) as ctx:
            preresearch.require(self.project)
        self.assertEqual(ctx.exception.code, "PRECOPY_RESEARCH_REQUIRED")

    def test_scaffold_alone_cannot_pass(self):
        cli = _preresearch_cli()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["init", "--project", str(self.project)]), 0)
        report = preresearch.check(self.project)
        self.assertFalse(report["ok"])
        self.assertEqual(report["state"], "INCOMPLETE")
        self.assertTrue(any("evidence-list.json" in p for p in report["problems"]))

    def test_init_never_overwrites_existing_artifacts(self):
        cli = _preresearch_cli()
        folder = self.project / preresearch.RESEARCH_DIR
        folder.mkdir(parents=True, exist_ok=True)
        _write_text(folder / "outline.md", "# Keep me\n")
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["init", "--project", str(self.project)])
        self.assertEqual((folder / "outline.md").read_text(encoding="utf-8"),
                         "# Keep me\n")

    def test_complete_artifacts_await_a_named_approval(self):
        _valid_artifacts(self.project)
        report = preresearch.check(self.project)
        self.assertFalse(report["ok"])
        self.assertEqual(report["state"], "AWAITING_APPROVAL")
        self.assertIn("approve", report["remedy"])

    def test_incomplete_evidence_blocks_even_with_all_files(self):
        _valid_artifacts(self.project)
        (self.project / preresearch.RESEARCH_DIR / "evidence-list.json").write_text(
            json.dumps({"items": []}) + "\n", encoding="utf-8")
        report = preresearch.check(self.project)
        self.assertFalse(report["ok"])
        self.assertEqual(report["state"], "INCOMPLETE")

    def test_boundary_must_state_non_production_claims(self):
        _valid_artifacts(self.project)
        _write_text(self.project / preresearch.RESEARCH_DIR / "boundary.md",
                    "# Boundary\n\nWe will render and publish this soon.\n")
        report = preresearch.check(self.project)
        self.assertFalse(report["ok"])
        self.assertTrue(any("production_ready: false" in p for p in report["problems"]))

    def test_approve_requires_reviewer_and_written_opinion(self):
        _valid_artifacts(self.project)
        with self.assertRaises(preresearch.PreresearchError) as ctx:
            preresearch.approve(self.project, reviewer="", opinion="reason")
        self.assertEqual(ctx.exception.code, "REVIEWER_REQUIRED")
        with self.assertRaises(preresearch.PreresearchError) as ctx:
            preresearch.approve(self.project, reviewer="Founder", opinion="")
        self.assertEqual(ctx.exception.code, "OPINION_REQUIRED")
        self.assertFalse((self.project / preresearch.RECEIPT).is_file())

    def test_approve_requires_a_green_check(self):
        with self.assertRaises(preresearch.PreresearchError) as ctx:
            preresearch.approve(self.project, reviewer="Founder", opinion="reason")
        self.assertEqual(ctx.exception.code, "ARTIFACTS_MISSING")

    def test_approval_is_bound_to_the_research_fingerprint(self):
        _valid_artifacts(self.project)
        record = preresearch.approve(self.project, reviewer="Founder",
                                     opinion="Read the sources")
        self.assertEqual(record["status"], "APPROVED")
        self.assertEqual(record["artifacts_sha256"], preresearch.fingerprint(self.project))
        self.assertTrue(preresearch.check(self.project)["ok"])

        # Any edit after signing makes the approval stale, with no force switch.
        outline = self.project / preresearch.RESEARCH_DIR / "outline.md"
        outline.write_text(outline.read_text(encoding="utf-8") + "\n- Extra beat.\n",
                           encoding="utf-8")
        report = preresearch.check(self.project)
        self.assertFalse(report["ok"])
        self.assertEqual(report["state"], "STALE")

    def test_receipt_never_claims_production_or_publication(self):
        _valid_artifacts(self.project)
        preresearch.approve(self.project, reviewer="Founder", opinion="Read the sources")
        receipt = json.loads((self.project / preresearch.RECEIPT).read_text(
            encoding="utf-8"))
        self.assertFalse(receipt["production_ready"])
        self.assertFalse(receipt["publish_authorized"])

    def test_stable_production_gates_include_the_research_gate(self):
        self.assertIn("precopy_research", gates.GATES)
        source = (ROOT / "scripts" / "production_gates.py").read_text(encoding="utf-8")
        self.assertEqual(source.count('add("precopy_research"'), 2,
                         "both VIDEO and GRAPHIC_TEXT gate sets must check research")

    # -- the intent binding: research always belongs to one routed topic ------

    def test_research_without_a_routed_intent_is_not_started(self):
        report = preresearch.check(self.project)
        self.assertEqual(len(report["missing"]), 5)
        self.assertTrue(any(m.endswith("content-intent.json")
                            for m in report["missing"]))
        self.assertIsNone(report["route_mode"])
        self.assertIsNone(report["intent_bound_to_brief"])

    def test_scaffold_must_still_be_bound_to_an_intent(self):
        cli = _preresearch_cli()
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["init", "--project", str(self.project)])
        report = preresearch.check(self.project)
        self.assertEqual(report["state"], "INCOMPLETE")
        self.assertTrue(any("content-intent.json" in p for p in report["problems"]))
        self.assertIn("preresearch.py intent", report["remedy"])

    def test_intent_route_mode_must_be_one_of_the_two_entrances(self):
        _valid_artifacts(self.project, _intent(route_mode="GUESSED"))
        report = preresearch.check(self.project)
        self.assertEqual(report["state"], "INCOMPLETE")
        self.assertTrue(any("route_mode" in p for p in report["problems"]))

    def test_hotspot_intent_must_name_the_selected_candidate(self):
        stripped = _intent("HOTSPOT_DISCOVERY")
        stripped["route_context"].pop("candidate_id")
        _valid_artifacts(self.project, stripped)
        report = preresearch.check(self.project)
        self.assertEqual(report["state"], "INCOMPLETE")
        self.assertTrue(any("candidate_id" in p for p in report["problems"]))

        _valid_artifacts(self.project, _intent("HOTSPOT_DISCOVERY"))
        report = preresearch.check(self.project)
        self.assertEqual(report["state"], "AWAITING_APPROVAL")
        self.assertEqual(report["topic_origin"], "HOTSPOT_SELECTION")
        self.assertEqual(report["candidate_id"], "CAND-TEST01")

    def test_direct_topic_intent_needs_no_candidate(self):
        _valid_artifacts(self.project, _intent("USER_TOPIC"))
        report = preresearch.check(self.project)
        self.assertEqual(report["state"], "AWAITING_APPROVAL")
        self.assertEqual(report["topic_origin"], "USER_INPUT")

    def test_topic_origin_must_match_the_route_mode(self):
        crossed = _intent("USER_TOPIC")
        crossed["route_context"]["topic_origin"] = "HOTSPOT_SELECTION"
        _valid_artifacts(self.project, crossed)
        report = preresearch.check(self.project)
        self.assertEqual(report["state"], "INCOMPLETE")
        self.assertTrue(any("topic_origin" in p for p in report["problems"]))

    def test_bind_intent_copies_the_router_intent_verbatim(self):
        intent = _intent("HOTSPOT_DISCOVERY")
        _write_text(self.project / preresearch.BRIEF_FILE, _brief(intent))
        payload = preresearch.bind_intent(self.project)
        self.assertEqual(payload["state"], "INTENT_BOUND")
        self.assertEqual(payload["candidate_id"], "CAND-TEST01")
        written = json.loads((self.project / preresearch.INTENT_FILE).read_text(
            encoding="utf-8"))
        self.assertEqual(written, intent)

        report = preresearch.check(self.project)
        self.assertTrue(report["intent_bound_to_brief"])

    def test_graphic_brief_at_the_same_path_is_not_a_router_intent(self):
        """`00_brief/brief.json` is shared; only the router dialect binds."""
        _valid_artifacts(self.project, _intent("USER_TOPIC"))
        _write_text(self.project / preresearch.BRIEF_FILE,
                    json.dumps({"schema": "contentops.graphic-brief/v1",
                                "bundle_id": "B-1", "title": "Graphic brief",
                                "platform": "wechat"}, ensure_ascii=False))
        report = preresearch.check(self.project)
        self.assertEqual(report["state"], "AWAITING_APPROVAL")
        self.assertIsNone(report["intent_bound_to_brief"])
        with self.assertRaises(preresearch.PreresearchError) as ctx:
            preresearch.bind_intent(self.project)
        self.assertEqual(ctx.exception.code, "NO_ROUTED_INTENT")

    def test_bind_intent_refuses_to_invent_a_topic(self):
        with self.assertRaises(preresearch.PreresearchError) as ctx:
            preresearch.bind_intent(self.project)
        self.assertEqual(ctx.exception.code, "NO_ROUTED_INTENT")
        self.assertFalse((self.project / preresearch.INTENT_FILE).is_file())

    def test_bind_intent_cannot_re_point_an_approved_package(self):
        _valid_artifacts(self.project, _intent("USER_TOPIC"))
        preresearch.approve(self.project, reviewer="Founder", opinion="Read the sources")
        self.assertTrue(preresearch.check(self.project)["ok"])

        other = _intent("USER_TOPIC", topic="A completely different topic")
        _write_text(self.project / preresearch.BRIEF_FILE, _brief(other))
        with self.assertRaises(preresearch.PreresearchError) as ctx:
            preresearch.bind_intent(self.project)
        self.assertEqual(ctx.exception.code, "ALREADY_APPROVED")

    def test_re_routing_invalidates_research_without_touching_the_receipt(self):
        """Re-route the topic and the same approval must stop applying."""
        _valid_artifacts(self.project, _intent("USER_TOPIC"))
        receipt_before = preresearch.approve(self.project, reviewer="Founder",
                                             opinion="Read the sources")
        self.assertTrue(preresearch.check(self.project)["ok"])

        re_routed = _intent("HOTSPOT_DISCOVERY", topic="A topic the router picked later")
        _write_text(self.project / preresearch.BRIEF_FILE, _brief(re_routed))
        report = preresearch.check(self.project)
        self.assertFalse(report["ok"])
        self.assertEqual(report["state"], "INCOMPLETE")
        self.assertFalse(report["intent_bound_to_brief"])
        self.assertTrue(any("brief.json" in p for p in report["problems"]))
        # the receipt itself is untouched: the binding is what refuses
        self.assertEqual(json.loads((self.project / preresearch.RECEIPT).read_text(
            encoding="utf-8")), receipt_before)

    def test_cli_approve_requires_explicit_confirmation(self):
        cli = _preresearch_cli()
        _valid_artifacts(self.project)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["approve", "--project", str(self.project),
                             "--reviewer", "Founder", "--opinion", "read"])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(payload["code"], "CONFIRMATION_REQUIRED")
        self.assertFalse((self.project / preresearch.RECEIPT).is_file())

    def test_cli_end_to_end_init_fill_check_approve(self):
        cli = _preresearch_cli()
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["init", "--project", str(self.project)])
        _valid_artifacts(self.project)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            check_code = cli.main(["check", "--project", str(self.project)])
        self.assertEqual(check_code, 4)  # artifacts ready, approval missing

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            approve_code = cli.main(["approve", "--project", str(self.project),
                                     "--reviewer", "Founder", "--opinion",
                                     "Verified the sources", "--confirm"])
        self.assertEqual(approve_code, 0)
        self.assertTrue(preresearch.check(self.project)["ok"])

    def test_copy_review_cli_cannot_sign_copy_without_research(self):
        """The copy decision is blocked even when called directly."""
        path = ROOT / "scripts" / "copy_review.py"
        spec = importlib.util.spec_from_file_location("copy_review_cli_gate", path)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        cli.ROOT = Path(self.tmp.name)
        project = self.project
        (project / "script").mkdir(parents=True, exist_ok=True)
        _write_text(project / "script" / "master.md", "# Draft copy\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main([str(project), "--approve", "--reviewer", "Founder",
                             "--opinion", "Approved copy", "--confirm", "--json"])
        payload = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(payload["state"], "BLOCKED")
        self.assertEqual(payload["code"], "PRECOPY_RESEARCH_REQUIRED")
        self.assertFalse((project / "receipts" / "script-review.json").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
