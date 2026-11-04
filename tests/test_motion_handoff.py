"""External motion handoff contract: a record is not a licence to use or publish.

Run: python tests/test_motion_handoff.py
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media import motion_handoff  # noqa: E402


def _fixture(tmp: str):
    project = Path(tmp) / "proj"
    (project / "assets" / "motion").mkdir(parents=True, exist_ok=True)
    asset = project / "assets" / "motion" / "m1.mp4"
    asset.write_bytes(b"motion")
    digest = hashlib.sha256(b"motion").hexdigest()
    payload = {
        "schema": "contentops.motion-handoff/v1",
        "asset_id": "motion-m1",
        "account_role": "explorer",
        "status": "RECEIVED",
        "runtime": {"name": "MotionClone", "version": "2.0.0",
                    "commit": "d21241f0a4b3acbb34c97dae47fa417b7065e438",
                    "hyperframes_version": "0.8.33"},
        "project": {"original_sha256": "a" * 64, "rearranged_sha256": "b" * 64},
        "output": {"path": "project://assets/motion/m1.mp4", "sha256": digest,
                   "duration_s": 6.0, "width": 1080, "height": 1920,
                   "fps": 30.0, "silent": True, "codec": "h264",
                   "pix_fmt": "yuv420p"},
        "source_window": {"start_s": 10.0, "end_s": 16.0},
        "rights": {"scope": "OWNED_SELF_MADE", "reviewed_by": "owner",
                   "reviewed_at": "2026-11-04", "evidence": "receipts/rights.json"},
        "generated": True,
        "evidence_capable": False,
        "publish_authorized": False,
    }
    return project, payload


def _raises(code, fn):
    try:
        fn()
    except motion_handoff.HandoffError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected HandoffError {code}")


def test_a_valid_handoff_is_accepted_for_review_only():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        result = motion_handoff.validate_handoff(payload, project_root=project)
    assert result["state"] == "ACCEPTED_FOR_REVIEW"
    assert result["asset_id"] == "motion-m1"
    assert result["generated"] is True
    assert result["evidence_capable"] is False
    assert result["production_ready"] is False
    assert result["publish_authorized"] is False
    assert result["rights"]["public_reuse_authorized"] is False


def test_receipt_is_not_a_licence_and_must_not_be_published():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        payload["rights"]["scope"] = "PUBLIC_REUSE"
        _raises("HANDOFF_RIGHTS_SCOPE",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))
        payload["rights"]["scope"] = "OWNED_SELF_MADE"
        payload["publish_authorized"] = True
        _raises("HANDOFF_FLAGS",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))


def test_generated_material_is_never_evidence():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        payload["evidence_capable"] = True
        _raises("HANDOFF_FLAGS",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))


def test_absolute_and_escaping_paths_are_refused():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        payload["output"]["path"] = "D:/Projects/x/assets/motion/m1.mp4"
        _raises("HANDOFF_PATH_ABSOLUTE",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))
        payload["output"]["path"] = "project://../escape.mp4"
        _raises("HANDOFF_PATH_ESCAPE",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))
        payload["output"]["path"] = "repo://assets/motion/m1.mp4"
        _raises("HANDOFF_PATH_SCHEME",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))


def test_missing_file_and_hash_mismatch_are_refused():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        payload["output"]["path"] = "project://assets/motion/missing.mp4"
        _raises("HANDOFF_FILE_MISSING",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))
        project, payload = _fixture(tmp)
        payload["output"]["sha256"] = "0" * 64
        _raises("HANDOFF_HASH_MISMATCH",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))


def test_runtime_must_be_the_pinned_pair():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        payload["runtime"]["hyperframes_version"] = "0.8.222"
        _raises("HANDOFF_RUNTIME_MISMATCH",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))
        payload["runtime"]["hyperframes_version"] = "0.8.33"
        payload["runtime"]["version"] = "1.0.0"
        _raises("HANDOFF_RUNTIME_MISMATCH",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))


def test_project_hashes_are_required_and_hex():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        payload["project"]["original_sha256"] = ""
        _raises("HANDOFF_PROJECT_HASH",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))
        payload["project"]["original_sha256"] = "not-a-hash"
        _raises("HANDOFF_PROJECT_HASH",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))


def test_source_window_must_be_short_and_ordered():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        payload["source_window"] = {"start_s": 16.0, "end_s": 10.0}
        _raises("HANDOFF_SOURCE_WINDOW",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))
        payload["source_window"] = {"start_s": 0.0, "end_s": 20.0}
        _raises("HANDOFF_SOURCE_WINDOW",
                lambda: motion_handoff.validate_handoff(payload, project_root=project))


def test_rejected_or_stale_status_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        for status in ("REJECTED", "STALE", "PENDING"):
            payload["status"] = status
            _raises("HANDOFF_STATUS",
                    lambda: motion_handoff.validate_handoff(payload, project_root=project))


def test_a_probe_with_audio_or_wrong_dimensions_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        probe = {"has_audio": True, "width": 1080, "height": 1920,
                 "codec_name": "h264", "pix_fmt": "yuv420p",
                 "avg_frame_rate": "30/1", "r_frame_rate": "30/1",
                 "duration_s": 6.0, "frame_timestamps": [i / 30 for i in range(180)]}
        _raises("HANDOFF_AUDIO_PRESENT",
                lambda: motion_handoff.validate_handoff(payload, project_root=project, probe=probe))
        probe["has_audio"] = False
        probe["width"] = 720
        _raises("HANDOFF_PROBE",
                lambda: motion_handoff.validate_handoff(payload, project_root=project, probe=probe))


def test_a_valid_probe_is_accepted_without_granting_publication():
    with tempfile.TemporaryDirectory() as tmp:
        project, payload = _fixture(tmp)
        probe = {"has_audio": False, "width": 1080, "height": 1920,
                 "codec_name": "h264", "pix_fmt": "yuv420p",
                 "avg_frame_rate": "30/1", "r_frame_rate": "30/1",
                 "duration_s": 6.0, "frame_timestamps": [i / 30 for i in range(180)]}
        result = motion_handoff.validate_handoff(payload, project_root=project, probe=probe)
    assert result["state"] == "ACCEPTED_FOR_REVIEW"
    assert result["publish_authorized"] is False
    assert result["production_ready"] is False


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - a runner reports, it does not hide
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    total = len(TESTS)
    print(f"{total - failures}/{total} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
