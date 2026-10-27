"""Redaction lineage and context-preserving crop tests.

Real ffmpeg is used on a synthetic clip, so the mask is checked by pixel rather
than by trusting the filter string. No capture or provider call is involved.

Run: python tests/test_context_preservation.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import redact_terminal_evidence as redaction  # noqa: E402
from contentops.evidence._common import ContractError  # noqa: E402
from contentops.evidence.capture import CaptureProof  # noqa: E402
from process_utils import hidden_run  # noqa: E402

_WORK = None


def _clip(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=12:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(path),
    ], timeout=120)
    assert result.returncode == 0 and path.exists(), result.stderr


def project_fixture() -> Path:
    """One project with a raw clip and its capture receipt, built once."""
    global _WORK
    if _WORK is not None:
        return _WORK
    work = Path(tempfile.mkdtemp(prefix="contentops-redaction-"))
    project = work / "project"
    raw = project / "work" / "raw" / "cap.mp4"
    _clip(raw)
    import hashlib
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    proof = CaptureProof(
        capture_id="CAP-TEST-001",
        session_id="CAP-TEST-001",
        evidence_class="EXECUTED",
        repository_revision="a" * 40,
        working_tree_state="clean",
        target_environment={"name": "test"},
        command={"display": "git rev-parse HEAD", "sha256": "b" * 64},
        read_only=True,
        fixture_or_cache="none",
        started_at="2026-10-27T10:00:00Z",
        finished_at="2026-10-27T10:00:03Z",
        exit_code=0,
        recording={"logical_path": "project://work/raw/cap.mp4",
                   "sha256": digest, "time_range": "00:00.000-00:03.000"},
        permission_scope="internal_review",
    ).validate()
    receipts = project / "receipts" / "captures"
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / "CAP-TEST-001.json").write_text(
        json.dumps(proof.to_dict(), indent=2), encoding="utf-8")
    _WORK = project
    return project


def plan(**overrides):
    document = {
        "schema": "contentops.redaction-plan/v1",
        "redaction_id": "RED-TEST-001",
        "capture_receipt": "project://receipts/captures/CAP-TEST-001.json",
        "raw": "project://work/raw/cap.mp4",
        "output": "project://work/redacted/cap.mp4",
        "source_dimensions": {"width": 640, "height": 360},
        "masks": [{
            "mask_id": "M1",
            "reason": "account name",
            "time_range": "00:00.000-00:03.000",
            "rect": {"x": 0, "y": 0, "width": 200, "height": 60},
        }],
        "protected_regions": [{
            "name": "result-line",
            "why": "it carries the conclusion",
            "time_range": "00:00.000-00:03.000",
            "rect": {"x": 300, "y": 200, "width": 200, "height": 100},
        }],
        "audio_policy": "REMOVED",
        "review_status": "PENDING",
        "publishable_scope": False,
    }
    document.update(overrides)
    return document


def write_plan(document) -> Path:
    path = Path(tempfile.mkdtemp(prefix="contentops-redaction-plan-")) / "plan.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def refuses(code, document, project=None):
    try:
        redaction.validate_plan(document, project or project_fixture())
    except (redaction.RedactionRefused, ContractError) as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"a plan with {code=} was accepted")


def _gray(path: Path, x: int, y: int) -> int:
    result = hidden_run([
        "ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1",
        "-vf", f"crop=2:2:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ], timeout=60, text=False)
    assert result.returncode == 0 and len(result.stdout) >= 4, result.stderr
    return max(result.stdout[:4])


def test_a_mask_cannot_hide_a_protected_region():
    protected = plan()["protected_regions"][0]
    mask = plan()["masks"][0]
    overlap = {**mask, "rect": dict(protected["rect"])}
    refuses("MASK_HIDES_PROTECTED_CONTEXT",
            plan(masks=[overlap]))
    print("[ok] 1. a mask overlapping a conclusion-bearing region is refused")


def test_masks_must_stay_inside_the_frame():
    bad = plan()["masks"][0]
    refuses("MASK_OUT_OF_BOUNDS",
            plan(masks=[{**bad, "rect": {"x": 600, "y": 0, "width": 100, "height": 60}}]))
    print("[ok] 2. a mask outside the source frame is refused")


def test_the_raw_reference_must_be_the_captured_recording():
    refuses("RAW_NOT_THE_CAPTURE", plan(raw="project://work/raw/other.mp4"))
    print("[ok] 3. a derivative cannot claim a different raw file")


def test_redaction_removes_audio_and_proves_the_mask_by_pixel():
    project = project_fixture()
    result = redaction.redact(write_plan(plan()), project)
    output = project / "work" / "redacted" / "cap.mp4"
    assert result["status"] == "OK", result
    assert output.exists()

    from contentops.media.transport import ffprobe_json
    payload = ffprobe_json(output)
    assert not any(s.get("codec_type") == "audio" for s in payload.get("streams") or []), (
        "the derivative kept its audio track")

    assert _gray(output, 10, 10) < 20, "the masked area is not black"
    assert _gray(output, 500, 100) > 20, "the mask blacked out the whole frame"

    receipt = json.loads((project / "receipts" / "redactions" / "RED-TEST-001.json")
                         .read_text(encoding="utf-8"))
    assert receipt["raw_source"]["sha256"] != receipt["output"]["sha256"]
    assert receipt["audio_removed"] is True
    print("[ok] 4. redaction removes audio and blacks only the declared mask")


def test_a_crop_needs_a_context_crop_that_contains_it():
    project = project_fixture()
    redaction.redact(write_plan(plan()), project)
    receipt = "project://receipts/redactions/RED-TEST-001.json"

    context = redaction.crop(project, receipt, "CR-1", "0,0,400,300", 1.0,
                             "project://work/crops/CR-1.png")
    assert context["rect"] == {"x": 0, "y": 0, "width": 400, "height": 300}

    enlarged = redaction.crop(project, receipt, "CR-2", "50,50,100,80", 1.0,
                              "project://work/crops/CR-2.png",
                              context_crop_id="CR-1")
    assert enlarged["context_crop_id"] == "CR-1"

    try:
        redaction.crop(project, receipt, "CR-3", "350,250,100,100", 1.0,
                       "project://work/crops/CR-3.png", context_crop_id="CR-1")
    except redaction.RedactionRefused as exc:
        assert exc.code == "CROP_NOT_CONTAINED_BY_CONTEXT", exc
    else:
        raise AssertionError("an enlarged crop escaped its context crop")
    print("[ok] 5. an enlarged crop must be contained by its earlier context crop")


def test_duplicate_and_unknown_crops_are_refused():
    project = project_fixture()
    fresh = plan(redaction_id="RED-TEST-002",
                 output="project://work/redacted/cap6.mp4")
    redaction.redact(write_plan(fresh), project)
    receipt = "project://receipts/redactions/RED-TEST-002.json"
    redaction.crop(project, receipt, "CR-1", "0,0,400,300", 1.0,
                   "project://work/crops/cap6-CR-1.png")
    try:
        redaction.crop(project, receipt, "CR-1", "0,0,200,200", 1.0,
                       "project://work/crops/again.png")
    except redaction.RedactionRefused as exc:
        assert exc.code == "DUPLICATE_CROP_ID", exc
    else:
        raise AssertionError("a duplicate crop id was accepted")

    try:
        redaction.crop(project, receipt, "CR-9", "0,0,200,200", 1.0,
                       "project://work/crops/CR-9.png",
                       context_crop_id="CR-404")
    except redaction.RedactionRefused as exc:
        assert exc.code in ("UNKNOWN_CONTEXT_CROP",), exc
    else:
        raise AssertionError("an unknown context crop was accepted")
    print("[ok] 6. duplicate crop ids and unknown context crops are refused")


def test_a_changed_derivative_invalidates_its_crops():
    project = project_fixture()
    receipt = "project://receipts/redactions/RED-TEST-001.json"
    output = project / "work" / "redacted" / "cap.mp4"
    with output.open("ab") as handle:
        handle.write(b"tamper")
    try:
        redaction.crop(project, receipt, "CR-X", "0,0,100,100", 1.0,
                       "project://work/crops/CR-X.png")
    except (redaction.RedactionRefused, ContractError) as exc:
        assert exc.code == "EVIDENCE_SHA_MISMATCH", exc
    else:
        raise AssertionError("a crop was taken from a modified derivative")
    finally:
        output.write_bytes(output.read_bytes()[:-6])
    print("[ok] 7. a derivative changed after its receipt blocks every crop")


def main() -> int:
    failures = []
    tests = (
        test_a_mask_cannot_hide_a_protected_region,
        test_masks_must_stay_inside_the_frame,
        test_the_raw_reference_must_be_the_captured_recording,
        test_redaction_removes_audio_and_proves_the_mask_by_pixel,
        test_a_crop_needs_a_context_crop_that_contains_it,
        test_duplicate_and_unknown_crops_are_refused,
        test_a_changed_derivative_invalidates_its_crops,
    )
    try:
        for fn in tests:
            try:
                fn()
            except AssertionError as exc:
                failures.append((fn.__name__, str(exc)))
                print(f"[FAIL] {fn.__name__}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failures.append((fn.__name__, repr(exc)))
                print(f"[ERR ] {fn.__name__}: {exc!r}")
    finally:
        if _WORK is not None:
            shutil.rmtree(_WORK.parent, ignore_errors=True)
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} redaction/context tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
