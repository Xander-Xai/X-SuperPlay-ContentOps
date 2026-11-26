"""Shared source and native graphic projection; synthetic fixtures only."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from contentops.workflow import shared_copy, preresearch, copy_review
from contentops.content_kernel.handoff import build_handoff, write_handoff, VIDEO, GRAPHIC_TEXT
from contentops.graphic import build_package, write_package, GraphicPackageError
from contentops.platforms.multichannel import MultiChannelAdapter, AdapterError
import graphic_offline
from test_script_draft import _sandbox, _approved_topic, TOPIC
from test_graphic_workflow import _project, _input


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class SharedCopyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = _sandbox(tmp.name).resolve()
        self.source = _approved_topic(self.root)
        self.graphic = self.root / "projects" / "graphic"
        self.graphic.mkdir()
        _project(self.graphic)
        preresearch.bind_intent(self.source)
        folder = self.source / preresearch.RESEARCH_DIR
        (folder / "project-reading.md").write_text(
            "# Project read-through\n\n## Files read\n- docs/RUNBOOK.md records stable commands.\n"
            "- scripts/copy_review.py records decisions.\n- src/contentops/workflow/copy_review.py computes fingerprints.\n\n"
            "## Findings\n- A copy decision is bound to a fingerprint.\n", encoding="utf-8")
        (folder / "outline.md").write_text("# Outline\n\n## Topic\n- One source claim.\n\n## Video\n- One shot.\n\n## Graphic\n- One draft preserving the same wording and evidence.\n\n## Evidence\n- Three sources; no measured runtime result or publication claim.\n", encoding="utf-8")
        write(folder / "evidence-list.json", {"schema": "contentops.precopy-research-evidence/v1", "items": [
            {"id": "S1", "kind": "primary", "title": "Fixture one", "url": "https://example.org/a"},
            {"id": "S2", "kind": "primary", "title": "Fixture two", "url": "https://example.org/b"},
            {"id": "S3", "kind": "official", "title": "Fixture three", "url": "https://example.org/c"}]})
        (folder / "boundary.md").write_text("# Boundary\n\nThis phase does not render or publish.\n- `production_ready: false`\n- `publish_authorized: false`\n- Research approval is not copy approval.\n", encoding="utf-8")
        preresearch.approve(self.source, reviewer="Fixture", opinion="synthetic research")
        self.text = "LangGraph uses a graph state."
        self.evidence = self.source / "script" / "evidence.txt"
        self.evidence.parent.mkdir(exist_ok=True)
        self.evidence.write_text(self.text, encoding="utf-8")
        item = {"evidence_id": "E-01", "kind": "document", "sha256": hashlib.sha256(self.evidence.read_bytes()).hexdigest(),
                "logical_path": "project://script/evidence.txt", "permission_scope": "publishable"}
        claim = {"claim_id": "C-01", "revision": 1, "text": self.text, "kind": "source", "assertion_about": "source",
                 "support_status": "SUPPORTED", "permission_scope": "publishable", "limitation": "",
                 "evidence": [item], "appearances": [{"surface": "narration", "text": self.text}]}
        write(self.source / "script/claim-map.json", {"schema": "contentops.claim-map/v1", "map_id": "CM-01", "package_id": self.source.name, "claims": [claim]})
        write(self.source / "script/lines.json", {"schema": "contentops.audio-first-lines/v1", "beats": [{"placement_id": "P-01", "claim_id": "C-01", "text": self.text}]})
        write(self.source / "script/storyboard.json", {"shots": [{"narration": self.text, "claim": "C-01"}]})
        (self.source / "script/master.md").write_text(self.text, encoding="utf-8")
        write(self.source / "00_brief/source-permissions.json", {"schema": "contentops.source-permissions/v1", "permissions": {"E-01": {"permission": "OWNED"}}})
        copy_review.decide(self.source, status_value="APPROVED", reviewer="Fixture", opinion="synthetic copy",
                           reviewed_at="2026-11-26T00:00:00Z")
        bundle = json.loads((ROOT / "projects/bundle-dual-line/bundle.json").read_text(encoding="utf-8"))
        bundle["source"]["topic_thesis"] = TOPIC
        self.bundle = self.root / "bundle.json"
        write(self.bundle, bundle)
        for project, fmt, platform in ((self.source, VIDEO, "bilibili"), (self.graphic, GRAPHIC_TEXT, "wechat_article")):
            handoff = build_handoff(bundle, "thinktank", fmt, project_slug=project.name,
                                    source_map={bundle["source"]["source_id"]: "fixture"},
                                    bundle_path=self.bundle, repo_root=self.root, project_dir=project,
                                    platform_id=platform, registry_root=ROOT)
            path = write_handoff(project, handoff)
            if fmt == GRAPHIC_TEXT:
                self.handoff = path

    def package(self):
        record = shared_copy.prepare(self.root, self.source, self.graphic)
        input_path = _input(self.graphic, title=TOPIC, draft="shared-copy.md", shared_copy=True)
        package = build_package(self.graphic, self.handoff, input_path, ROOT, self.root, bundle_root=self.root)
        write_package(self.graphic, package, self.root)
        return record, package

    def test_shared_copy_and_native_export(self):
        record, package = self.package()
        self.assertEqual(package["shared_copy"]["shared_copy_id"], record["shared_copy_id"])
        self.assertEqual(shared_copy.verify_video(self.root, self.source), record)
        self.assertEqual((self.graphic / "shared-copy.md").read_text(encoding="utf-8").strip(), self.text)
        result = graphic_offline.build(self.root, self.graphic, ["wechat_article", "zhihu", "csdn", "juejin", "toutiao", "weibo"])
        self.assertEqual(len(result["platforms"]), 6)
        native = {p["platform"]: p["native_format"] for p in result["platforms"]}
        self.assertEqual(native["wechat_article"], "html")
        self.assertEqual(native["zhihu"], "markdown")
        self.assertEqual(native["weibo"], "text")
        self.assertFalse(result["publish_authorized"])
        self.assertEqual(result["external_action"], "none")
        with self.assertRaises(ValueError):
            graphic_offline.build(self.root, self.graphic, ["x"])
        with self.assertRaises(ValueError):
            graphic_offline.build(self.root, self.graphic, ["xiaohongshu_image"])

    def test_video_production_requires_converted_inputs(self):
        record, _ = self.package()
        from unittest.mock import patch
        from contentops.script import m5_bridge
        with patch.object(m5_bridge, "check", return_value={"ok": True, "problems": []}):
            self.assertEqual(shared_copy.verify_video_production(self.root, self.source), record)
        with patch.object(m5_bridge, "check", return_value={"ok": False, "problems": ["script/script.json changed"]}):
            with self.assertRaises(shared_copy.SharedCopyError):
                shared_copy.verify_video_production(self.root, self.source)

    def test_drift_blocks_both_paths(self):
        _, package = self.package()
        self.evidence.write_text("Changed", encoding="utf-8")
        with self.assertRaises(shared_copy.SharedCopyError):
            shared_copy.verify_video(self.root, self.source)
        with self.assertRaises(shared_copy.SharedCopyError):
            shared_copy.verify_package(self.root, self.graphic, package)

    def test_graphic_copy_tamper_blocks(self):
        _, package = self.package()
        (self.graphic / "shared-copy.md").write_text("Invented results", encoding="utf-8")
        with self.assertRaises(shared_copy.SharedCopyError):
            shared_copy.verify_package(self.root, self.graphic, package)
        with self.assertRaises(ValueError):
            graphic_offline.build(self.root, self.graphic, ["zhihu"])

    def test_research_stale_blocks(self):
        self.package()
        (self.source / preresearch.RESEARCH_DIR / "outline.md").write_text("Changed", encoding="utf-8")
        with self.assertRaises(shared_copy.SharedCopyError):
            shared_copy.verify_video(self.root, self.source)



    def test_native_draft_review_preserves_lineage(self):
        import native_editorial_draft as native
        self.package()
        draft = native.current(self.root, self.graphic, "zhihu")
        draft["title"] = "How does graph state work?"
        draft["title_review_note"] = "Fixture title matches the one claim"
        draft["reviewer"] = "Fixture reviewer"
        draft["claims"][0]["draft_text"] = "LangGraph uses graph state."
        draft["claims"][0]["review_note"] = "Fixture paraphrase; no new fact"
        out = native.review(self.root, self.graphic, "zhihu", draft)
        self.assertEqual(out["status"], "REVIEWED_DRAFT_ONLY")
        self.assertFalse(out["publish_authorized"])
        self.assertEqual(out["claim_ids"], ["C-01"])
        self.assertIn("LangGraph uses graph state.", out["native_preview"]["body"])
        self.assertEqual((self.graphic / "shared-copy.md").read_text(encoding="utf-8").strip(), self.text)
        draft["claims"][0]["evidence"] = []
        with self.assertRaisesRegex(ValueError, "lineage modified"):
            native.review(self.root, self.graphic, "zhihu", draft)

    def test_native_draft_missing_review_and_stale(self):
        import native_editorial_draft as native
        self.package()
        draft = native.current(self.root, self.graphic, "csdn")
        with self.assertRaisesRegex(ValueError, "reviewer"):
            native.review(self.root, self.graphic, "csdn", draft)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            native.current(self.root, self.graphic, "x")
        self.evidence.write_text("Changed", encoding="utf-8")
        with self.assertRaises(ValueError):
            native.review(self.root, self.graphic, "csdn", draft)


if __name__ == "__main__":
    unittest.main()
