#!/usr/bin/env python3
"""Tests for the recording intake gate.

What this pins down
-------------------
* **Policy before pixels.** A ``FORBIDDEN`` account is refused before the file is looked at,
  so a banned format cannot reach a render. An account that never declared itself is blocked
  rather than defaulted to something permissive.
* **The crop is a contract, not a comment.** ``ALLOWED_CROPPED`` without a rectangle is
  blocked, and a rectangle that leaves the frame is blocked too.
* **Evidence is not distribution.** An admitted recording is written with
  ``evidence_capable: true`` *and* ``distribution_authorized: false`` /
  ``requires_human_review: true``, and the receipt always carries both false flags.
* **A refusal leaves a trace.** Every verdict writes ``receipts/recording-intake.json``;
  a refusal nobody can audit is a refusal nobody can review.

Run: python tests/test_recording_intake.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from contentops.media import recording_intake as ri  # noqa: E402

PROBE = {"format": {"duration": "12.5"},
         "streams": [{"codec_type": "video", "codec_name": "h264",
                      "width": 1920, "height": 1080, "duration": "12.5"}]}


def _probe(_path):
    return PROBE


def _write_account(root: Path, slug: str, manual_recording: str) -> None:
    (root / "config" / "accounts" / f"{slug}.json").write_text(json.dumps({
        "schema": "contentops.account-dna/v1",
        "slug": slug,
        "account": slug,
        "evidence": {"mode": "EVIDENCE_LED", "manual_recording": manual_recording},
    }, ensure_ascii=False), encoding="utf-8")


def _workspace(tmp: Path, *, manual_recording: str = "ALLOWED_CROPPED",
               slug: str = "demo-account", declare_slug: bool = True,
               claim_ids: list[str] | None = None) -> tuple[Path, Path]:
    root = tmp / "repo"
    (root / "config" / "accounts").mkdir(parents=True, exist_ok=True)
    (root / "projects").mkdir(exist_ok=True)
    _write_account(root, slug, manual_recording)
    project = root / "projects" / "demo"
    (project / "script").mkdir(parents=True, exist_ok=True)
    lines = ["schema: contentops.project/v1"]
    if declare_slug:
        lines.append(f"account_slug: {slug}")
    (project / "project.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if claim_ids is not None:
        (project / "script" / "claim-map.json").write_text(json.dumps({
            "schema": "contentops.claim-map/v1",
            "claims": [{"claim_id": item, "text": f"claim {item}"} for item in claim_ids],
        }, ensure_ascii=False), encoding="utf-8")
    return root, project


def _clip(tmp: Path, name: str = "terminal.mp4") -> Path:
    path = tmp / "captures" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"payload" * 8)
    return path


def _request(path: Path, **kwargs):
    kwargs.setdefault("claim_ids", ["C01"])
    return ri.RecordingRequest(path=path, **kwargs)


def test_forbidden_account_is_refused_before_the_file_is_read():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path, manual_recording="FORBIDDEN", slug="fi")
        result = ri.intake(project, _request(tmp_path / "missing.mp4"), repo_root=root,
                           probe=_probe)
        assert result["verdict"] == ri.REFUSED, result
        assert result["reason_code"] == "RECORDING_FORBIDDEN_BY_DNA", result
        assert "FORBIDDEN" in result["reason"], result["reason"]


def test_refusal_still_writes_a_receipt():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path, manual_recording="FORBIDDEN", slug="fi")
        ri.intake(project, _request(_clip(tmp_path)), repo_root=root, probe=_probe)
        receipt = json.loads((project / ri.RECEIPT).read_text(encoding="utf-8"))
        assert receipt["verdict"] == ri.REFUSED, receipt
        assert receipt["production_ready"] is False, receipt
        assert receipt["publish_authorized"] is False, receipt
        assert not (project / ri.MANIFEST).exists()


def test_undeclared_account_is_blocked_not_defaulted():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path, declare_slug=False)
        result = ri.intake(project, _request(_clip(tmp_path)), repo_root=root, probe=_probe)
        assert result["verdict"] == ri.BLOCKED, result
        assert result["reason_code"] == "ACCOUNT_UNANNOUNCED", result


def test_cropped_account_without_a_rectangle_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path, manual_recording="ALLOWED_CROPPED")
        result = ri.intake(project, _request(_clip(tmp_path)), repo_root=root, probe=_probe)
        assert result["verdict"] == ri.BLOCKED, result
        assert result["reason_code"] == "CROP_REQUIRED", result


def test_crop_outside_the_frame_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path, manual_recording="ALLOWED_CROPPED")
        request = _request(_clip(tmp_path), crop={"x": 1500, "y": 0,
                                                 "width": 800, "height": 600})
        result = ri.intake(project, request, repo_root=root, probe=_probe)
        assert result["verdict"] == ri.BLOCKED, result
        assert result["reason_code"] == "CROP_OUT_OF_BOUNDS", result


def test_unknown_claim_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path, claim_ids=["C01"])
        request = _request(_clip(tmp_path), claim_ids=["C99"],
                           crop={"x": 0, "y": 100, "width": 1080, "height": 900})
        result = ri.intake(project, request, repo_root=root, probe=_probe)
        assert result["verdict"] == ri.BLOCKED, result
        assert result["reason_code"] == "CLAIM_UNKNOWN", result
        assert result["bindings"][0]["resolved"] is False, result["bindings"]


def test_accepted_recording_is_evidence_capable_but_not_publishable():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path, claim_ids=["C01"])
        request = _request(_clip(tmp_path), claim_ids=["C01"],
                           crop={"x": 0, "y": 100, "width": 1080, "height": 900},
                           source_ref="repo://src/contentops/media")
        result = ri.intake(project, request, repo_root=root, probe=_probe)
        assert result["verdict"] == ri.ACCEPTED, result
        assert result["production_ready"] is False, result
        assert result["publish_authorized"] is False, result
        row = json.loads((project / ri.MANIFEST).read_text(encoding="utf-8"))["assets"][0]
        assert row["type"] == "recording", row
        assert row["origin"] == "SELF_CAPTURED", row
        assert row["evidence_capable"] is True, row
        assert row["distribution_authorized"] is False, row
        assert row["requires_human_review"] is True, row
        assert row["claim_ids"] == ["C01"], row
        assert row["frame_size"] == {"width": 1920, "height": 1080}, row
        copied = project / row["repo_path"].replace("project://", "")
        assert copied.is_file(), row["repo_path"]


def test_second_intake_of_the_same_bytes_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path, claim_ids=["C01"])
        request = _request(_clip(tmp_path), claim_ids=["C01"],
                           crop={"x": 0, "y": 100, "width": 1080, "height": 900})
        ri.intake(project, request, repo_root=root, probe=_probe)
        again = ri.intake(project, request, repo_root=root, probe=_probe)
        assert again["verdict"] == ri.ACCEPTED, again
        assert again["idempotent"] is True, again
        assets = json.loads((project / ri.MANIFEST).read_text(encoding="utf-8"))["assets"]
        assert len(assets) == 1, assets


def test_dry_run_decides_without_writing_the_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path, claim_ids=["C01"])
        request = _request(_clip(tmp_path), claim_ids=["C01"],
                           crop={"x": 0, "y": 100, "width": 1080, "height": 900})
        result = ri.intake(project, request, repo_root=root, probe=_probe, apply=False)
        assert result["verdict"] == ri.ACCEPTED, result
        assert result["applied"] is False, result
        assert not (project / ri.MANIFEST).exists()
        assert not (project / "assets").exists()


def test_unknown_policy_value_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path, manual_recording="SOMETIMES")
        result = ri.intake(project, _request(_clip(tmp_path)), repo_root=root, probe=_probe)
        assert result["verdict"] == ri.BLOCKED, result
        assert result["reason_code"] == "POLICY_UNKNOWN", result


def test_probe_failure_blocks_rather_than_admitting():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root, project = _workspace(tmp_path)
        def boom(_path):
            raise RuntimeError("ffprobe missing")
        result = ri.intake(project, _request(_clip(tmp_path)), repo_root=root, probe=boom)
        assert result["verdict"] == ri.BLOCKED, result
        assert result["reason_code"] == "PROBE_FAILED", result


# --- runner ------------------------------------------------------------------

TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a test runner reports, it does not raise
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
