"""Offline tests for local BGM rights, mood selection and loudness-aware mixing.

CI runs this file directly: ``python tests/test_bgm_planner.py``. No ffmpeg,
no audio vendor, no paid call: loudness measurements are injected.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.audio import AudioMeasurements  # noqa: E402
from contentops.media import bgm_planner as bgm  # noqa: E402


def _measure(path=None):
    return AudioMeasurements(duration_s=30.0, integrated_lufs=-20.0,
                             true_peak_db=-3.0, peak_db=-4.0,
                             loudness_range_lu=5.0)


def _track_row(name, data, *, moods, permission="OWNED", with_rights=False):
    row = {
        "id": f"bgm-{name}", "type": "BGM", "permission": permission,
        "license": "OWNED-BY-OPERATOR", "author": "Founder",
        "source_url": "", "sha256": hashlib.sha256(data).hexdigest(),
        "repo_relative_path": f"assets/bgm/{name}.wav", "moods": moods,
    }
    if with_rights:
        row["rights"] = {}
    return row


def _manifest(project, rows):
    path = project / "sources" / "assets.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": bgm.MANIFEST_SCHEMA, "assets": rows},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "repo" / "projects" / "p1"
        (self.project / "assets" / "bgm").mkdir(parents=True)

    def test_no_manifest_means_no_bgm_and_no_download(self):
        index = bgm.index_local_tracks(self.project, measure=_measure)
        self.assertEqual(index["state"], "NO_LOCAL_TRACKS")
        selection = bgm.select_track(index, account_slug="x-superplay-1024")
        self.assertEqual(selection["state"], "NO_LICENSED_TRACK")
        plan = bgm.no_bgm_plan(selection["reason"])
        self.assertEqual(plan["state"], "NO_BGM")
        self.assertFalse(plan["download_attempted"])
        self.assertEqual(bgm.attribution_manifest(selection)["items"], [])

    def test_hash_mismatch_and_pending_rights_are_refused(self):
        good = b"RIFF-WAVE-calm"
        bad = b"RIFF-WAVE-changed"
        (self.project / "assets" / "bgm" / "calm.wav").write_bytes(bad)
        (self.project / "assets" / "bgm" / "pending.wav").write_bytes(good)
        _manifest(self.project, [
            _track_row("calm", good, moods=["calm"]),
            _track_row("pending", good, moods=["calm"], permission="LICENSED"),
        ])
        index = bgm.index_local_tracks(self.project, measure=_measure)
        self.assertEqual(index["state"], "NO_LICENSED_TRACK")
        by_id = {row["asset_id"]: row for row in index["tracks"]}
        self.assertFalse(by_id["bgm-calm"]["usable"])
        self.assertTrue(any("sha256" in r for r in by_id["bgm-calm"]["reasons"]))
        self.assertEqual(by_id["bgm-pending"]["rights_state"], "PENDING_HUMAN_REVIEW")
        self.assertFalse(by_id["bgm-pending"]["usable"])

    def test_owned_hash_verified_track_is_indexed_with_loudness(self):
        data = b"RIFF-WAVE-calm"
        (self.project / "assets" / "bgm" / "calm.wav").write_bytes(data)
        (self.project / "assets" / "bgm" / "energetic.wav").write_bytes(b"RIFF-WAVE-fast")
        _manifest(self.project, [
            _track_row("calm", data, moods=["calm", "focused"]),
            _track_row("energetic", b"RIFF-WAVE-fast", moods=["energetic"]),
        ])
        index = bgm.index_local_tracks(self.project, measure=_measure)
        self.assertEqual(index["state"], "READY")
        self.assertEqual(index["usable_count"], 2)
        row = index["tracks"][0]
        self.assertEqual(row["integrated_lufs"], -20.0)
        self.assertEqual(row["true_peak_db"], -3.0)
        self.assertEqual(row["rights_state"], "CLEARED_LOCAL")


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.index = {
            "schema": bgm.SCHEMA, "state": "READY",
            "tracks": [
                {"asset_id": "calm", "path": "calm.wav", "sha256": "a" * 64,
                 "license_id": "OWNED-BY-OPERATOR", "author": "Founder",
                 "moods": ["calm"], "duration_s": 30.0,
                 "integrated_lufs": -20.0, "true_peak_db": -3.0,
                 "rights_state": "CLEARED_LOCAL", "usable": True},
                {"asset_id": "energetic", "path": "energetic.wav", "sha256": "b" * 64,
                 "license_id": "OWNED-BY-OPERATOR", "author": "Founder",
                 "moods": ["energetic"], "duration_s": 30.0,
                 "integrated_lufs": -14.0, "true_peak_db": -3.0,
                 "rights_state": "CLEARED_LOCAL", "usable": True},
            ],
        }

    def test_account_dna_and_content_type_pick_the_matching_mood(self):
        engineering = bgm.select_track(
            self.index, account_slug="x-superplay-future-intelligence",
            content_type="engineering_deep_dive")
        self.assertEqual(engineering["selected"]["asset_id"], "calm")
        demo = bgm.select_track(
            self.index, account_slug="x-superplay-1024",
            content_type="product_demo")
        self.assertEqual(demo["selected"]["asset_id"], "energetic")
        self.assertTrue(engineering["rejected"])

    def test_attribution_manifest_is_generated_from_real_metadata(self):
        selection = bgm.select_track(self.index,
                                     account_slug="x-superplay-future-intelligence")
        manifest = bgm.attribution_manifest(selection)
        self.assertEqual(manifest["state"], "REQUIRED")
        self.assertEqual(len(manifest["items"]), 1)
        self.assertIn("Founder", manifest["credits_text"])
        self.assertEqual(manifest["items"][0]["license_id"], "OWNED-BY-OPERATOR")


class MixPlanTests(unittest.TestCase):
    def test_gain_is_derived_from_measured_lufs_not_a_fixed_percentage(self):
        voice = AudioMeasurements(integrated_lufs=-16.0, true_peak_db=-2.0,
                                  loudness_range_lu=4.0, duration_s=65.9)
        quiet = AudioMeasurements(integrated_lufs=-25.0, true_peak_db=-6.0, duration_s=90.0)
        loud = AudioMeasurements(integrated_lufs=-14.0, true_peak_db=-2.0, duration_s=90.0)
        quiet_plan = bgm.build_mix_plan(voice, quiet, target_duration_s=65.9)
        loud_plan = bgm.build_mix_plan(voice, loud, target_duration_s=65.9)
        self.assertEqual(quiet_plan["state"], "PLANNED")
        self.assertEqual(quiet_plan["target_track_lufs"], -34.0)
        self.assertEqual(quiet_plan["gain_db"], -9.0)
        self.assertEqual(loud_plan["gain_db"], -20.0)
        self.assertNotEqual(quiet_plan["gain_db"], loud_plan["gain_db"])
        self.assertNotEqual(quiet_plan["duck"]["makeup_db"], loud_plan["duck"]["makeup_db"])
        self.assertIn("measured", quiet_plan["gain_basis"])

    def test_unmeasured_audio_refuses_to_guess_a_volume(self):
        voice = AudioMeasurements(integrated_lufs=None)
        track = AudioMeasurements(integrated_lufs=None)
        plan = bgm.build_mix_plan(voice, track, target_duration_s=30.0)
        self.assertEqual(plan["state"], "UNMEASURED_AUDIO")
        self.assertFalse(plan["bgm_enabled"])
        self.assertIn("no fixed volume fallback", plan["reason"])

    def test_true_peak_ceiling_clamps_gain_and_short_track_loops_at_input(self):
        voice = AudioMeasurements(integrated_lufs=-16.0, true_peak_db=-2.0)
        hot = AudioMeasurements(integrated_lufs=-50.0, true_peak_db=0.0,
                                duration_s=8.0)
        plan = bgm.build_mix_plan(voice, hot, target_duration_s=65.9)
        self.assertTrue(any("clamped" in c for c in plan["loudness_checks"]))
        self.assertEqual(plan["input"]["stream_loop"], -1)
        self.assertTrue(plan["duration"]["loop"])
        self.assertIn("sidechaincompress", plan["ffmpeg_filter_complex"])
        self.assertIn("afade=t=in", plan["ffmpeg_filter_complex"])
        self.assertIn("atrim", plan["ffmpeg_filter_complex"])

    def test_duck_threshold_follows_the_voice_loudness(self):
        quiet_voice = AudioMeasurements(integrated_lufs=-22.0, true_peak_db=-4.0)
        loud_voice = AudioMeasurements(integrated_lufs=-14.0, true_peak_db=-2.0)
        track = AudioMeasurements(integrated_lufs=-20.0, true_peak_db=-3.0, duration_s=90.0)
        self.assertLess(
            bgm.build_mix_plan(quiet_voice, track, target_duration_s=30.0)["duck"]["threshold_db"],
            bgm.build_mix_plan(loud_voice, track, target_duration_s=30.0)["duck"]["threshold_db"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
