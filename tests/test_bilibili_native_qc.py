#!/usr/bin/env python3
"""Offline native-canvas QC tests: dimensions are not publication or layout proof."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import qc_video  # noqa: E402


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


def test_native_source_geometry_requires_every_shot_to_be_landscape():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        wide = project / "wide.png"
        portrait = project / "portrait.png"
        wide.write_bytes(b"fixture")
        portrait.write_bytes(b"fixture")
        metadata = {
            str(wide): {"streams": [{"codec_type": "video", "width": 1920, "height": 1080}]},
            str(portrait): {"streams": [{"codec_type": "video", "width": 1080, "height": 1920}]},
        }
        storyboard = {"shots": [{"image": str(wide)}, {"video": str(portrait)}]}
        with mock.patch.object(qc_video, "ffprobe_meta", side_effect=lambda p: metadata[str(p)]):
            result = qc_video._native_source_geometry_check(project, storyboard)
        assert result["ok"] is False
        assert result["failed_shot_indices"] == [1]


def test_native_source_geometry_rejects_unverifiable_shots():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        storyboard = {"shots": [{"caption": "missing media source"}]}
        result = qc_video._native_source_geometry_check(project, storyboard)
        assert result["ok"] is False
        assert result["failed_shot_indices"] == [0]


def test_engineering_sample_visuals_are_generated_not_evidence():
    project = ROOT / "projects" / "e2e-p2-bilibili-169-sample"
    storyboard = json.loads((project / "script" / "storyboard.json").read_text(encoding="utf-8"))
    manifest = json.loads((project / "sources" / "assets.json").read_text(encoding="utf-8"))
    assert storyboard["shots"]
    assert all(shot["source_type"] == "generated"
               and shot["generated"] is True
               and shot["evidence_capable"] is False
               for shot in storyboard["shots"])
    assert all(asset["type"] == "generated_image"
               and asset["generated"] is True
               and asset["evidence_capable"] is False
               for asset in manifest["assets"])


def test_native_full_decode_checks_real_bytes():
    # Tiny generated technical fixture, never an account or production video.
    import shutil
    if shutil.which("ffmpeg") is None:
        raise AssertionError("ffmpeg is required for native decode regression")
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "fixture.mp4"
        result = qc_video.hidden_run(
            ["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
             "color=c=black:s=64x64:r=10:d=0.5", "-c:v", "mpeg4", "-y", str(path)],
            capture_output=True, timeout=30)
        assert result.returncode == 0, result.returncode
        sha = qc_video._file_sha256(path)
        good = qc_video._native_full_decode(path, sha)
        assert good["ok"] and good["sha256"] == sha, good
        changed = qc_video._native_full_decode(path, "0" * 64)
        assert changed["code"] == "MEDIA_CHANGED_BEFORE_DECODE", changed
        path.write_bytes(b"not an mp4")
        corrupt = qc_video._native_full_decode(path, qc_video._file_sha256(path))
        assert not corrupt["ok"] and corrupt["severity"] == "FAIL", corrupt


def test_native_full_decode_detects_mutation():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "fixture.mp4"
        path.write_bytes(b"before")
        sha = qc_video._file_sha256(path)
        def mutate(*args, **kwargs):
            path.write_bytes(b"after")
            return mock.Mock(returncode=0)
        with mock.patch.object(qc_video, "hidden_run", side_effect=mutate):
            result = qc_video._native_full_decode(path, sha)
        assert result["code"] == "MEDIA_CHANGED_DURING_DECODE", result


def main() -> int:
    tests = (test_legacy_default_stays_vertical,
             test_horizontal_requires_explicit_native_target_and_storyboard,
             test_geometry_checks_are_orientation_specific,
             test_native_source_geometry_requires_every_shot_to_be_landscape,
             test_native_source_geometry_rejects_unverifiable_shots,
             test_engineering_sample_visuals_are_generated_not_evidence,
             test_native_full_decode_checks_real_bytes,
             test_native_full_decode_detects_mutation)
    for run in tests:
        run()
        print("PASS", run.__name__)
    print(f"{len(tests)}/{len(tests)} native QC contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
