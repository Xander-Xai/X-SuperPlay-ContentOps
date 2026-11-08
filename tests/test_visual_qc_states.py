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


class ShotReuseEvidenceTests(unittest.TestCase):
    """A rewritten variation must never release a repeated shot.

    Negative fixtures come from the A original film's renderer receipt
    (P-01..P-07 all carry source_asset_id=source-anchor-01 while their frames
    show large pixel deltas from subtitle/highlight/zoom only). Positive
    fixtures come from the A rebuilt film, whose placements use distinct
    source assets and measured content-band deltas of 22/11.09 and 41/18.43.
    """

    @staticmethod
    def _row(shot_id, anchor, dhash="0000000000000000", **extra):
        row = {"shot_id": shot_id, "asset_id": f"huashu-{shot_id}",
               "frame_dhash": dhash, "source_asset_id": anchor}
        row.update(extra)
        return row

    def test_variation_text_alone_never_releases_a_repeat(self):
        rows = [self._row("P-02", "source-anchor-01", variation="overview"),
                self._row("P-03", "source-anchor-01", variation="different detail")]
        issue = qc_visual._shot_reuse_issues(rows)[0]
        self.assertEqual(issue["state"], "FAIL")
        self.assertIn("same_source_asset_id", issue["evidence_gaps"])

    def test_old_film_consecutive_same_anchor_is_flagged_even_with_large_frame_delta(self):
        # Measured on the old film's midpoint frames: 103/240 and 13.71 MAE,
        # then 118/240 and 12.97 MAE. Still the same full-frame screenshot.
        rows = [self._row("P-02", "source-anchor-01", variation="config settings"),
                self._row("P-03", "source-anchor-01", variation="cross reranker",
                          content_hamming_delta=103, content_mae=13.71),
                self._row("P-04", "source-anchor-01", variation="semantic cache",
                          content_hamming_delta=118, content_mae=12.97)]
        issues = qc_visual._shot_reuse_issues(rows)
        self.assertEqual(len(issues), 2)
        self.assertTrue(all(i["state"] == "FAIL" for i in issues))
        self.assertTrue(all(i["type"] == "REPEATED_SOURCE_WITHOUT_PURPOSE" for i in issues))

    def test_new_film_distinct_assets_with_measured_content_change_is_allowed(self):
        for delta, mae in ((22, 11.09), (41, 18.43)):
            with self.subTest(delta=delta, mae=mae):
                rows = [self._row("seg-03-config-ranking", "seg-03-config-ranking"),
                        self._row("seg-03-config-guardrails", "seg-03-config-guardrails",
                                  content_hamming_delta=delta, content_mae=mae)]
                issue = qc_visual._shot_reuse_issues(rows)[0]
                self.assertEqual(issue["state"], "ALLOWED_WITH_VERIFIED_VISUAL_EVIDENCE")
                self.assertIn("measured_frame_content_change", issue["evidence_basis"])

    def test_same_anchor_local_crop_reuse_is_allowed(self):
        rows = [self._row("P-02", "source-anchor-01", crop_region=(0.0, 0.1, 1.0, 0.4)),
                self._row("P-03", "source-anchor-01", crop_region=(0.0, 0.5, 1.0, 0.9),
                          content_hamming_delta=22, content_mae=11.09)]
        issue = qc_visual._shot_reuse_issues(rows)[0]
        self.assertEqual(issue["state"], "ALLOWED_WITH_VERIFIED_VISUAL_EVIDENCE")
        self.assertIn("structured_crop_or_ocr_region", issue["evidence_basis"])

    def test_free_text_focus_is_not_accepted_as_visual_evidence(self):
        rows = [self._row("P-02", "source-anchor-01", crop="lines 1-20"),
                self._row("P-03", "source-anchor-01", crop="lines 21-40",
                          content_hamming_delta=103, content_mae=13.71)]
        self.assertIsNone(qc_visual.structured_region(rows[0]))
        self.assertEqual(qc_visual._shot_reuse_issues(rows)[0]["state"], "FAIL")

    def test_missing_measured_change_stays_fail(self):
        rows = [self._row("seg-05-engine-benchmark", "seg-05-engine-benchmark"),
                self._row("seg-06-retriever-overview", "seg-06-retriever-overview")]
        self.assertEqual(qc_visual._shot_reuse_issues(rows)[0]["state"], "FAIL")

    def test_near_duplicate_threshold_is_unchanged(self):
        self.assertEqual(qc_visual.NEAR_DUPLICATE_DHASH_MAX, 3)
        rows = [self._row("S1", "A", dhash="0000000000000000"),
                self._row("S2", "B", dhash="0000000000000007")]  # distance 3
        self.assertEqual(len(qc_visual._shot_reuse_issues(rows)), 1)
        rows[1]["frame_dhash"] = "000000000000000f"  # distance 4
        self.assertEqual(len(qc_visual._shot_reuse_issues(rows)), 0)

    def test_legacy_placement_ids_resolve_to_their_source_anchor(self):
        anchors = {"P-02": "source-anchor-01"}
        shot = {"shot_id": "huashu-P-02__002", "asset_id": "huashu-P-02"}
        self.assertEqual(qc_visual.source_asset_for(shot, shot["shot_id"], anchors),
                         "source-anchor-01")


if __name__ == "__main__":
    unittest.main(verbosity=2)
