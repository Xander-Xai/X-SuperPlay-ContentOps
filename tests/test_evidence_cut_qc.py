"""Target-aware evidence QC tests.

Run: python tests/test_evidence_cut_qc.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.media.cut_qc import MIN_REAL_SOURCE_RATIO, qc_cut, source_shares  # noqa: E402
from process_utils import hidden_run  # noqa: E402

SHA = "a" * 64


def _clip(path: Path, width=320, height=180, seconds=4.5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=15:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(path),
    ], timeout=120)
    assert result.returncode == 0 and path.exists(), result.stderr


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _placement(pid, start, end, asset, claims=None, bearing=True):
    return {
        "placement_id": pid, "start_ms": start, "end_ms": end,
        "asset_id": asset, "source_time_range": "00:00.000-00:04.500",
        "crop": {"x": 0, "y": 0, "width": 320, "height": 180,
                 "source_width": 320, "source_height": 180},
        "reading_class": "reading", "semantic_progress": "shows the result",
        "claim_ids": claims or [], "caption_cue_ids": [],
        "claim_bearing": bearing, "context_first": False,
        "context_placement_id": None, "transition": "cut",
    }


def make_project(td: Path, *, generated: bool = False, width=320, height=180,
                 max_hold=5000) -> Path:
    project = td / "project"
    clip = project / "work" / "raw" / "cap.mp4"
    _clip(clip, width=width, height=height)
    final = project / "final" / "easel.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(clip, final)

    assets = {
        "A-REAL": {"kind": "recording",
                   "path": "project://work/raw/cap.mp4", "sha256": _sha(clip)},
    }
    placements = [_placement("P-1", 0, 2000 if generated else 4500,
                             "A-REAL", ["C-1"])]
    if generated:
        assets["A-GEN"] = {"kind": "generated_video",
                           "path": "project://work/raw/cap.mp4",
                           "sha256": _sha(clip)}
        placements.append(_placement("P-2", 2000, 4000, "A-GEN", [], bearing=False))
    (project / "script").mkdir(parents=True, exist_ok=True)
    (project / "script" / "assets.json").write_text(
        json.dumps({"schema": "contentops.asset-map/v1", "assets": assets}), encoding="utf-8")
    (project / "script" / "cut-plan.json").write_text(json.dumps({
        "schema": "contentops.cut-plan/v1", "package_id": "qc-fixture",
        "target": {"width": width, "height": height,
                   "duration_ms_range": [4000, 5000],
                   **({"max_visual_hold_ms": max_hold} if max_hold else {}),
                   "caption_safe_area": {"x": 10, "y": 120, "width": 300, "height": 50}},
        "placements": placements,
    }), encoding="utf-8")
    (project / "script" / "claim-map.json").write_text(json.dumps({
        "schema": "contentops.claim-map/v1", "map_id": "MAP-QC", "package_id": "qc-fixture",
        "claims": [{
            "claim_id": "C-1", "revision": 1, "text": "测试通过。",
            "kind": "runtime", "assertion_about": "cli",
            "support_status": "SUPPORTED", "permission_scope": "internal",
            "limitation": "",
            "evidence": [{"evidence_id": "E-1", "kind": "terminal_recording",
                          "sha256": _sha(clip), "logical_path": "project://work/raw/cap.mp4",
                          "time_range": None, "permission_scope": "internal"}],
            "appearances": [
                {"surface": "narration", "text": "测试通过。", "time_range": "00:00.000-00:02.000"},
                {"surface": "caption", "text": "测试通过。", "time_range": "00:00.000-00:02.000"}],
        }],
    }), encoding="utf-8")
    captions = project / "assets" / "captions" / "cut.srt"
    captions.parent.mkdir(parents=True, exist_ok=True)
    captions.write_text("1\n00:00:00,000 --> 00:00:02,000\n测试通过。\n", encoding="utf-8")
    cover = project / "assets" / "covers" / "cover.png"
    cover.parent.mkdir(parents=True, exist_ok=True)
    hidden_run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"color=c=0xF2EDE4:s={width}x{height}",
                "-frames:v", "1", str(cover)], timeout=60)
    (project / "receipts").mkdir(parents=True, exist_ok=True)
    (project / "receipts" / "cover.json").write_text(json.dumps({
        "schema": "contentops.cover-receipt/v1",
        "png": {"path": "project://assets/covers/cover.png", "sha256": _sha(cover)},
    }), encoding="utf-8")
    return project


def test_overlapping_intervals_count_once():
    shares = source_shares(
        SimpleNamespace(placements=[
            SimpleNamespace(asset_id="R1", start_ms=0, end_ms=3000),
            SimpleNamespace(asset_id="R1", start_ms=1000, end_ms=5000),
        ]),
        {"R1": {"kind": "recording"}},
    )
    assert abs(shares["real_s"] - 5.0) < 0.01, shares
    print("[ok] 1. overlapping real intervals are counted once")


def test_duration_weighting_defeats_the_shot_count_trick():
    shares = source_shares(
        SimpleNamespace(placements=[
            SimpleNamespace(asset_id="R1", start_ms=0, end_ms=2000),
            SimpleNamespace(asset_id="G1", start_ms=2000, end_ms=12000),
        ]),
        {"R1": {"kind": "recording"}, "G1": {"kind": "generated_video"}},
    )
    assert shares["real_ratio"] < MIN_REAL_SOURCE_RATIO, shares
    assert shares["generated_ratio"] > 0.10, shares
    print("[ok] 2. 2 s real + 10 s generated fails on duration, not shot count")


def test_a_valid_target_passes_and_a_wrong_size_fails():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td))
        report = qc_cut(project)
        assert report["overall"] == "PASS", report["checks"]

        # Replace the render with a different size; the target, not a constant,
        # decides.
        _clip(project / "final" / "easel.mp4", width=640, height=360)
        report = qc_cut(project)
        bad = [c for c in report["checks"] if c["id"] == "resolution"]
        assert bad and not bad[0]["ok"], bad
        assert report["overall"] == "FAIL"
    print("[ok] 3. target dimensions are enforced from the CutPlan")


def test_a_long_generated_interval_fails_the_cut():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), generated=True)
        report = qc_cut(project)
        gen = [c for c in report["checks"] if c["id"] == "generated_ratio"][0]
        assert not gen["ok"], gen
        assert report["overall"] == "FAIL"
    print("[ok] 4. a generated interval above 10% fails the cut")


def test_missing_captions_fail_closed():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td))
        (project / "assets" / "captions" / "cut.srt").unlink()
        report = qc_cut(project)
        captions = [c for c in report["checks"] if c["id"] == "captions_present"][0]
        assert not captions["ok"], captions
        assert report["overall"] == "FAIL"
    print("[ok] 5. missing captions fail the gate")


def test_a_long_undeclared_static_view_fails():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=None)  # default 2000ms
        report = qc_cut(project)
        views = [c for c in report["checks"] if c["id"] == "views_declared"][0]
        assert not views["ok"], views
        assert report["overall"] == "FAIL"
    print("[ok] 6. a placement over the hold limit must declare its views")


def test_a_frozen_render_fails_the_static_hold_gate():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=2000)
        plan_path = project / "script" / "cut-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["placements"] = [
            _placement("P-1", 0, 2000, "A-REAL", ["C-1"]),
            _placement("P-1b", 2000, 4000, "A-REAL", ["C-1"]),
        ]
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        # Two 2 s placements satisfy the structure, but the render itself is one
        # frozen image for four seconds: the measured gate must still catch it.
        frozen = project / "final" / "easel.mp4"
        result = hidden_run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=0x101010:s=320x180:r=15:d=4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(frozen),
        ], timeout=120)
        assert result.returncode == 0, result.stderr
        report = qc_cut(project)
        hold = [c for c in report["checks"] if c["id"] == "static_hold_within_limit"][0]
        assert not hold["ok"], hold
        assert report["overall"] == "FAIL"
    print("[ok] 7. a frozen render fails even when the plan declares its views")


def main() -> int:
    tests = (
        test_overlapping_intervals_count_once,
        test_duration_weighting_defeats_the_shot_count_trick,
        test_a_valid_target_passes_and_a_wrong_size_fails,
        test_a_long_generated_interval_fails_the_cut,
        test_missing_captions_fail_closed,
        test_a_long_undeclared_static_view_fails,
        test_a_frozen_render_fails_the_static_hold_gate,
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
    print(f"\nAll {len(tests)} cut-QC tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
