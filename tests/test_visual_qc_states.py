"""Quality-state layering must stay honest and independently derivable.

The regression this prevents: ``quality_states.technical`` used to be gated on
canonical QC ``overall == "PASS"``. A film whose only WARN was
``real_evidence_present`` (an editorial finding, not a media defect) was
reported as TECHNICAL_PENDING even though ffprobe, resolution, codecs and audio
all passed. Conversely, publication approval was a hard-coded constant that no
technical or visual PASS may ever turn into an approval.

Pure-offline suite: no ffmpeg, no network, no provider, no video files.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import qc_visual  # noqa: E402


def _canonical(overall: str = "PASS", technical_fail: str | None = None,
               evidence_warn: bool = True) -> dict:
    checks = [{"id": "_video", "ok": True, "severity": "INFO"}]
    for cid in qc_visual.TECHNICAL_CHECK_IDS:
        checks.append({
            "id": cid,
            "ok": cid != technical_fail,
            "severity": "FAIL" if cid == technical_fail else "PASS",
        })
    checks.append({
        "id": "real_evidence_present",
        "ok": not evidence_warn,
        "severity": "WARN" if evidence_warn else "PASS",
    })
    checks.append({"id": "voice_quality_declared", "ok": True, "severity": "INFO"})
    return {"overall": overall, "checks": checks}


def _write_review(project: Path, payload: dict) -> None:
    (project / "receipts").mkdir(parents=True, exist_ok=True)
    (project / "receipts" / "human-review.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ReceiptBindingTests(unittest.TestCase):
    def test_receipt_binds_the_exact_file_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "clip.mp4"
            clip.write_bytes(b"frame-bytes-0001")
            expected = hashlib.sha256(b"frame-bytes-0001").hexdigest()
            self.assertEqual(qc_visual.file_sha256(clip), expected)
            clip.write_bytes(b"frame-bytes-0002")
            self.assertNotEqual(qc_visual.file_sha256(clip), expected)

    def test_missing_file_is_not_reported_as_a_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(qc_visual.file_sha256(Path(tmp) / "absent.mp4"))


class TechnicalStateTests(unittest.TestCase):
    def test_editorial_warn_does_not_downgrade_a_decodable_file(self):
        canonical = _canonical(overall="WARN", evidence_warn=True)
        self.assertEqual(canonical["overall"], "WARN")
        self.assertEqual(qc_visual.technical_state(canonical), "TECHNICAL_PASS")

    def test_a_failed_media_check_is_a_technical_fail(self):
        canonical = _canonical(overall="FAIL", technical_fail="video_codec_h264")
        self.assertEqual(qc_visual.technical_state(canonical), "TECHNICAL_FAIL")

    def test_missing_media_checks_are_pending_not_pass(self):
        canonical = _canonical()
        canonical["checks"] = [row for row in canonical["checks"]
                               if row["id"] != "ffprobe_parse"]
        self.assertEqual(qc_visual.technical_state(canonical), "TECHNICAL_PENDING")

    def test_no_canonical_report_is_pending(self):
        self.assertEqual(qc_visual.technical_state({}), "TECHNICAL_PENDING")
        self.assertEqual(qc_visual.technical_state({"overall": "PASS"}),
                         "TECHNICAL_PENDING")

    def test_technical_layer_ignores_overall_entirely(self):
        passing = _canonical(overall="WARN")
        failing = _canonical(overall="PASS", technical_fail="audio_present")
        self.assertEqual(qc_visual.technical_state(passing), "TECHNICAL_PASS")
        self.assertEqual(qc_visual.technical_state(failing), "TECHNICAL_FAIL")


class HumanReviewStateTests(unittest.TestCase):
    def test_absent_review_stays_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                qc_visual.human_review_states(Path(tmp)),
                ("CONTENT_REVIEW_PENDING", "PENDING_HUMAN_APPROVAL"))

    def test_malformed_review_stays_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "receipts").mkdir()
            (project / "receipts" / "human-review.json").write_text(
                "{not json", encoding="utf-8")
            self.assertEqual(
                qc_visual.human_review_states(project),
                ("CONTENT_REVIEW_PENDING", "PENDING_HUMAN_APPROVAL"))

    def test_unsigned_or_unscored_review_is_not_an_approval(self):
        incomplete = [
            {"decision": "APPROVED", "production_ready": True,
             "reviewer": None, "reviewed_at": "2026-11-09T10:00:00+08:00",
             "scores": {"clarity": 5}},
            {"decision": "APPROVED", "production_ready": True,
             "reviewer": "founder", "reviewed_at": None,
             "scores": {"clarity": 5}},
            {"decision": "APPROVED", "production_ready": True,
             "reviewer": "founder", "reviewed_at": "2026-11-09T10:00:00+08:00",
             "scores": None},
            {"decision": "CHANGES_REQUESTED", "production_ready": True,
             "reviewer": "founder", "reviewed_at": "2026-11-09T10:00:00+08:00",
             "scores": {"clarity": 5}},
            {"decision": "APPROVED", "production_ready": False,
             "reviewer": "founder", "reviewed_at": "2026-11-09T10:00:00+08:00",
             "scores": {"clarity": 5}},
        ]
        for payload in incomplete:
            with self.subTest(payload=payload):
                with tempfile.TemporaryDirectory() as tmp:
                    project = Path(tmp)
                    _write_review(project, payload)
                    self.assertEqual(
                        qc_visual.human_review_states(project),
                        ("CONTENT_REVIEW_PENDING", "PENDING_HUMAN_APPROVAL"))

    def test_complete_real_review_is_the_only_publish_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write_review(project, {
                "decision": "APPROVED", "production_ready": True,
                "reviewer": "founder", "reviewed_at": "2026-11-09T10:00:00+08:00",
                "scores": {"clarity": 5, "evidence": 4},
            })
            self.assertEqual(
                qc_visual.human_review_states(project),
                ("CONTENT_REVIEWED", "PUBLISH_APPROVED"))

    def test_technical_and_visual_pass_never_approve_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            technical = qc_visual.technical_state(
                _canonical(overall="WARN", evidence_warn=True))
            _, publication = qc_visual.human_review_states(project)
            self.assertEqual(technical, "TECHNICAL_PASS")
            self.assertEqual(publication, "PENDING_HUMAN_APPROVAL")
            # A visual pass is a separate layer and is not an approval either.
            states = {"technical": technical, "visual": "VISUAL_PASS",
                      "content": "CONTENT_REVIEW_PENDING",
                      "publication": publication}
            self.assertNotEqual(states["publication"], "PUBLISH_APPROVED")
            self.assertEqual(states["content"], "CONTENT_REVIEW_PENDING")


if __name__ == "__main__":
    unittest.main(verbosity=2)
