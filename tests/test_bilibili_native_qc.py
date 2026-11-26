#!/usr/bin/env python3
"""Offline native-canvas QC tests: dimensions are not publication or layout proof."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import qc_video  # noqa: E402
from contentops.media.cut_qc import _within_account_duration  # noqa: E402


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_legacy_default_stays_vertical() -> None:
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        assert qc_video._expected_canvas(project) == (1080, 1920, "9:16")
        _write(project / "project.yaml", "id: sample\ntarget:\n  resolution: 1080x1920\n")
        assert qc_video._expected_canvas(project) == (1080, 1920, "9:16")


def test_horizontal_requires_explicit_native_target_and_storyboard() -> None:
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        _write(project / "project.yaml",
               "id: sample\ntarget:\n  resolution: 1920x1080\n")
        try:
            qc_video._expected_canvas(project)
        except ValueError as exc:
            assert "target.platform=bilibili" in str(exc)
        else:
            raise AssertionError("horizontal resolution alone must not authorize native QC")
        _write(project / "project.yaml",
               "id: sample\ntarget:\n  resolution: 1920x1080\n"
               "  platform: bilibili\n  native_relayout: true\n")
        _write(project / "script" / "storyboard.json", '{"size":"1080x1920"}')
        try:
            qc_video._expected_canvas(project)
        except ValueError as exc:
            assert "storyboard must declare" in str(exc)
        else:
            raise AssertionError("vertical storyboard cannot pass native acceptance")
        _write(project / "script" / "storyboard.json", '{"size":"1920x1080"}')
        assert qc_video._expected_canvas(project) == (1920, 1080, "16:9")


def test_account_duration_ceiling_is_account_specific() -> None:
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        _write(project / "project.yaml",
               "id: sample\naccount_slug: x-superplay-future-intelligence\n")
        assert qc_video._duration_bounds(project) == (30.0, 300.0)
        assert qc_video._duration_check(project, 300.0)["ok"]
        assert not qc_video._duration_check(project, 300.01)["ok"]
        future_dna = {"slug": "x-superplay-future-intelligence",
                      "narrative": {"target_duration_s": [30, 300]}}
        assert _within_account_duration(future_dna, 300.0)
        assert not _within_account_duration(future_dna, 300.01)
        _write(project / "project.yaml", "id: sample\naccount_slug: x-superplay-1024\n")
        assert qc_video._duration_bounds(project) == (30.0, 120.0)
        assert qc_video._duration_check(project, 120.0)["ok"]
        assert not qc_video._duration_check(project, 120.01)["ok"]
        assert _within_account_duration(
            {"slug": "x-superplay-1024", "narrative": {"target_duration_s": [45, 60]}},
            60.25)
        _write(project / "project.yaml", "id: sample\n")
        assert qc_video._duration_bounds(project) == (30.0, 120.0)


def test_geometry_checks_are_orientation_specific() -> None:
    vertical = qc_video._canvas_checks(1080, 1920, 1080, 1920, "9:16")
    assert all(row["ok"] for row in vertical)
    assert vertical[1]["id"] == "aspect_ratio_9_16"
    native = qc_video._canvas_checks(1920, 1080, 1920, 1080, "16:9")
    assert all(row["ok"] for row in native)
    assert native[1]["id"] == "aspect_ratio_16_9"
    recycled = qc_video._canvas_checks(1080, 1920, 1920, 1080, "16:9")
    assert all(not row["ok"] for row in recycled)
    wrong_resolution = qc_video._canvas_checks(1280, 720, 1920, 1080, "16:9")
    assert not wrong_resolution[0]["ok"] and wrong_resolution[1]["ok"]


def main() -> int:
    tests = (test_legacy_default_stays_vertical,
             test_horizontal_requires_explicit_native_target_and_storyboard,
             test_account_duration_ceiling_is_account_specific,
             test_geometry_checks_are_orientation_specific)
    for run in tests:
        run()
        print("PASS", run.__name__)
    print(f"{len(tests)}/{len(tests)} native QC contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
