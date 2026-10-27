"""Review-bundle binding tests.

Run: python tests/test_review_bundle.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.evidence._common import ContractError  # noqa: E402
from contentops.media.review_bundle import (  # noqa: E402
    build_review_bundle,
    record_review,
    validate_review_binding,
    write_review_bundle,
)
from process_utils import hidden_run  # noqa: E402


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clip(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=320x180:rate=15:duration=4",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(path),
    ], timeout=120)
    assert result.returncode == 0, result.stderr


def _wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-c:a", "pcm_s16le", str(path),
    ], timeout=120)
    assert result.returncode == 0, result.stderr


def make_project(td: Path, *, permission: str = "internal_review") -> Path:
    projects = td / "projects"
    project = projects / "evidence-fixture"
    capture_project = projects / "easel-evidence-capture"
    clip = project / "work" / "raw" / "cap.mp4"
    _clip(clip)
    (project / "final").mkdir(parents=True, exist_ok=True)
    shutil.copy2(clip, project / "final" / "easel.mp4")
    _wav(project / "work" / "narration.wav")
    captions = project / "assets" / "captions" / "cut.srt"
    captions.parent.mkdir(parents=True, exist_ok=True)
    captions.write_text("1\n00:00:00,000 --> 00:00:02,000\n测试通过。\n", encoding="utf-8")

    (project / "script").mkdir(parents=True, exist_ok=True)
    (project / "script" / "assets.json").write_text(json.dumps({
        "schema": "contentops.asset-map/v1",
        "assets": {"A-REAL": {"kind": "recording", "path": "project://work/raw/cap.mp4",
                              "sha256": _sha(clip), "capture_id": "CAP-1"}},
    }), encoding="utf-8")
    (project / "script" / "cut-plan.json").write_text(json.dumps({
        "schema": "contentops.cut-plan/v1", "package_id": "evidence-fixture",
        "target": {"width": 320, "height": 180, "duration_ms_range": [3000, 5000]},
        "placements": [{
            "placement_id": "P-1", "start_ms": 0, "end_ms": 4000,
            "asset_id": "A-REAL", "source_time_range": "00:00.000-00:04.000",
            "crop": {"x": 0, "y": 0, "width": 320, "height": 180,
                     "source_width": 320, "source_height": 180},
            "reading_class": "reading", "semantic_progress": "shows the result",
            "claim_ids": ["C-1"], "caption_cue_ids": [], "claim_bearing": True,
            "context_first": False, "context_placement_id": None, "transition": "cut",
        }],
    }), encoding="utf-8")
    (project / "script" / "claim-map.json").write_text(json.dumps({
        "schema": "contentops.claim-map/v1", "map_id": "MAP-1", "package_id": "evidence-fixture",
        "claims": [{
            "claim_id": "C-1", "revision": 1, "text": "测试通过。", "kind": "runtime",
            "assertion_about": "cli", "support_status": "SUPPORTED",
            "permission_scope": "internal", "limitation": "",
            "evidence": [{"evidence_id": "E-1", "kind": "terminal_recording",
                          "sha256": _sha(clip),
                          "logical_path": "project://work/raw/cap.mp4",
                          "time_range": None, "permission_scope": "internal"}],
            "appearances": [{"surface": "caption", "text": "测试通过。"}],
        }],
    }), encoding="utf-8")
    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / "qc-report.json").write_text(json.dumps({"overall": "PASS"}), encoding="utf-8")
    (receipts / "build-easel.json").write_text(json.dumps({"status": "OK"}), encoding="utf-8")

    proof = {
        "schema": "contentops.capture-proof/v1",
        "capture_id": "CAP-1", "session_id": "CAP-1", "evidence_class": "EXECUTED",
        "repository_revision": "a" * 40, "working_tree_state": "clean",
        "target_environment": {"name": "test"},
        "command": {"display": "git rev-parse HEAD", "sha256": "b" * 64},
        "read_only": True, "fixture_or_cache": "none",
        "started_at": "2026-10-27T10:00:00Z", "finished_at": "2026-10-27T10:00:04Z",
        "exit_code": 0,
        "recording": {"logical_path": "project://work/raw/cap.mp4",
                      "sha256": _sha(clip), "time_range": "00:00.000-00:04.000"},
        "permission_scope": permission, "notes": [],
    }
    cap_dir = capture_project / "receipts" / "captures"
    cap_dir.mkdir(parents=True, exist_ok=True)
    (cap_dir / "CAP-1.json").write_text(json.dumps(proof), encoding="utf-8")
    return project


def test_the_bundle_is_deterministic_and_blocks_internal_evidence():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td))
        first = build_review_bundle(project)
        second = build_review_bundle(project)
        assert first["review_bundle_fingerprint"] == second["review_bundle_fingerprint"]
        assert first["inputs"]["distribution_blocked"] is True, first["inputs"]
        assert first["status"] == "PENDING_HUMAN_REVIEW"
        assert first["production_ready"] is False
    print("[ok] 1. a bundle is deterministic and blocks unpublished evidence")


def test_changing_a_fingerprinted_input_invalidates_the_review():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td))
        bundle = write_review_bundle(project)
        recorded = bundle["review_bundle_fingerprint"]
        assert validate_review_binding(project, recorded)["ok"]

        captions = project / "assets" / "captions" / "cut.srt"
        captions.write_text("1\n00:00:00,000 --> 00:00:03,000\n测试通过。\n", encoding="utf-8")
        result = validate_review_binding(project, recorded)
        assert not result["ok"], result
    print("[ok] 2. a changed caption invalidates the recorded fingerprint")


def test_a_score_below_80_holds_and_80_becomes_ready():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td))
        write_review_bundle(project)
        held = record_review(project, "Founder", 79, False)
        assert held["status"] == "HOLD" and held["production_ready"] is False

        write_review_bundle(project)  # the review fields are not inputs
        ready = record_review(project, "Founder", 80, False)
        assert ready["status"] == "PRODUCTION_READY" and ready["production_ready"] is True
        assert "published" not in ready, "recording a review must not publish"
    print("[ok] 3. 79 holds; 80 with no hard fail becomes production-ready")


def test_a_failing_qc_or_a_stale_bundle_cannot_be_approved():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td))
        write_review_bundle(project)
        (project / "receipts" / "qc-report.json").write_text(
            json.dumps({"overall": "FAIL"}), encoding="utf-8")
        try:
            record_review(project, "Founder", 95, False)
        except ContractError as exc:
            assert exc.code == "STALE_REVIEW_BUNDLE" or exc.code == "QC_NOT_PASS", exc
        else:
            raise AssertionError("a failing QC report was approved")

        (project / "receipts" / "qc-report.json").write_text(
            json.dumps({"overall": "PASS"}), encoding="utf-8")
        write_review_bundle(project)
        (project / "assets" / "captions" / "cut.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n改过了。\n", encoding="utf-8")
        try:
            record_review(project, "Founder", 95, False)
        except ContractError as exc:
            assert exc.code == "STALE_REVIEW_BUNDLE", exc
        else:
            raise AssertionError("a stale bundle was approved")
    print("[ok] 4. a failing QC or a stale bundle cannot be approved")


def test_a_hard_fail_or_missing_reviewer_is_refused():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td))
        write_review_bundle(project)
        try:
            record_review(project, "Founder", 90, True)
        except ContractError as exc:
            assert exc.code == "HARD_FAIL", exc
        else:
            raise AssertionError("a hard fail was approved")

        try:
            record_review(project, "", 90, False)
        except ContractError as exc:
            assert exc.code == "MISSING_FIELD", exc
        else:
            raise AssertionError("an empty reviewer was accepted")
    print("[ok] 5. a hard fail or an unnamed reviewer is refused")


def main() -> int:
    tests = (
        test_the_bundle_is_deterministic_and_blocks_internal_evidence,
        test_changing_a_fingerprinted_input_invalidates_the_review,
        test_a_score_below_80_holds_and_80_becomes_ready,
        test_a_failing_qc_or_a_stale_bundle_cannot_be_approved,
        test_a_hard_fail_or_missing_reviewer_is_refused,
    )
    failures = []
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} review-bundle tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
