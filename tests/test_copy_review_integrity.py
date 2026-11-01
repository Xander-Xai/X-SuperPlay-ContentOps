"""The copy fingerprint must cover what the film shows and claims, not only what
it narrates.

The failure this prevents: a review is approved, then the clip behind a shot is
swapped, or the caption is rewritten, or a claim is rebound to different
evidence — and the fingerprint does not move, so a stale ``APPROVED`` still
passes. That was possible while ``video``, ``caption``, ``claim`` and ``source``
were absent from ``COPY_FIELDS``.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import copy_review  # noqa: E402


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _project(temp: Path) -> Path:
    """A minimal but realistic project: script, captions, asset map, media."""
    script = temp / "script"
    script.mkdir()
    (script / "master.md").write_text("# script\nhook line\n", encoding="utf-8")
    (script / "cut.srt").write_text(
        "1\n00:00:00,000 --> 00:00:05,000\n第一句\n", encoding="utf-8")
    (script / "lines.json").write_text(
        json.dumps({"lines": [{"line": 0, "text": "第一句"}]}, ensure_ascii=False),
        encoding="utf-8")
    (script / "claim-map.json").write_text(
        json.dumps({"claims": [{"id": "C1", "source": "A-ONE"}]}, ensure_ascii=False),
        encoding="utf-8")
    media = temp / "work" / "motion"
    media.mkdir(parents=True)
    clip = media / "beat-00.mp4"
    clip.write_bytes(b"clip bytes v1")
    (script / "assets.json").write_text(json.dumps({
        "schema": "contentops.asset-map/v1",
        "assets": {
            "A-ONE": {"kind": "motion", "path": "project://work/motion/beat-00.mp4",
                      "sha256": _sha(clip.read_bytes()), "evidence_capable": False},
        },
    }, ensure_ascii=False), encoding="utf-8")
    shot = {"unit": "u1", "narration": "第一句", "caption": "第一句",
            "claim": "C1", "image": None, "video": "project://work/motion/beat-00.mp4",
            "source": "project://work/motion/beat-00.mp4", "source_type": "motion",
            "duration": 5.0, "function": "proof", "dna_role": "support"}
    (script / "storyboard.json").write_text(json.dumps({
        "size": "1080x1920", "narration": "project://work/narration.wav",
        "subtitle": "project://assets/captions/cut.srt", "runtime": {"release": "v0.2.1"},
        "shots": [shot],
    }, ensure_ascii=False), encoding="utf-8")
    return temp


def _board(project: Path) -> dict:
    return json.loads((project / "script" / "storyboard.json").read_text(encoding="utf-8"))


def _write_board(project: Path, document: dict) -> None:
    (project / "script" / "storyboard.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _approve(project: Path) -> dict:
    return copy_review.decide(project, status_value="APPROVED", reviewer="test-reviewer",
                              opinion="fixture approval for a fingerprint test",
                              reviewed_at="2026-11-01T00:00:00Z")


def test_swapping_the_video_invalidates_the_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        assert copy_review.status(project)["state"] == "APPROVED"
        document = _board(project)
        document["shots"][0]["video"] = "project://work/motion/beat-01.mp4"
        _write_board(project, document)
        gate = copy_review.status(project)
        assert gate["state"] == "STALE", gate
        assert gate["ok"] is False


def test_changing_the_caption_invalidates_the_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        (project / "script" / "cut.srt").write_text(
            "1\n00:00:00,000 --> 00:00:05,000\n换了一句\n", encoding="utf-8")
        assert copy_review.status(project)["state"] == "STALE"


def test_changing_the_claim_binding_invalidates_the_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        document = _board(project)
        document["shots"][0]["claim"] = "C2"
        _write_board(project, document)
        assert copy_review.status(project)["state"] == "STALE"


def test_changing_the_source_invalidates_the_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        document = _board(project)
        document["shots"][0]["source"] = "project://sources/other.png"
        _write_board(project, document)
        assert copy_review.status(project)["state"] == "STALE"


def test_replacing_the_bytes_behind_an_unchanged_path_is_asset_drift():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        assert copy_review.status(project)["ok"] is True
        (project / "work" / "motion" / "beat-00.mp4").write_bytes(b"clip bytes v2")
        gate = copy_review.status(project)
        assert gate["state"] == "ASSET_DRIFT", gate
        assert gate["ok"] is False
        assert gate["asset_drift"][0]["asset_id"] == "A-ONE"


def test_missing_review_blocks():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        gate = copy_review.status(project)
        assert gate["state"] == "NOT_REVIEWED"
        assert gate["ok"] is False
        try:
            copy_review.require_approved(project)
        except copy_review.CopyReviewRequired:
            pass
        else:
            raise AssertionError("a missing review must raise")


def test_a_stale_sha_blocks():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        record = _approve(project)
        record["copy_sha256"] = "0" * 64
        (project / "receipts" / "script-review.json").write_text(
            json.dumps(record), encoding="utf-8")
        gate = copy_review.status(project)
        assert gate["state"] == "STALE"
        assert gate["ok"] is False


def test_build_metadata_does_not_invalidate_the_review():
    """Rewriting paths the pipeline owns must not force a new review."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        document = _board(project)
        document["narration"] = "project://work/narration-110x.wav"
        document["subtitle"] = "project://assets/captions/cut-110x.srt"
        document["runtime"] = {"release": "v0.2.1", "commit": "deadbeef"}
        document["engine"] = "easel"
        _write_board(project, document)
        gate = copy_review.status(project)
        assert gate["state"] == "APPROVED", gate


def test_declared_assets_are_part_of_the_fingerprint():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        before = copy_review.copy_fingerprint(project)
        assets = json.loads((project / "script" / "assets.json").read_text(encoding="utf-8"))
        assets["assets"]["A-ONE"]["sha256"] = "1" * 64
        (project / "script" / "assets.json").write_text(
            json.dumps(assets, ensure_ascii=False), encoding="utf-8")
        assert copy_review.copy_fingerprint(project) != before


def main() -> int:
    tests = (test_swapping_the_video_invalidates_the_review,
             test_changing_the_caption_invalidates_the_review,
             test_changing_the_claim_binding_invalidates_the_review,
             test_changing_the_source_invalidates_the_review,
             test_replacing_the_bytes_behind_an_unchanged_path_is_asset_drift,
             test_missing_review_blocks,
             test_a_stale_sha_blocks,
             test_build_metadata_does_not_invalidate_the_review,
             test_declared_assets_are_part_of_the_fingerprint)
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"All {len(tests)} copy-review integrity tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
