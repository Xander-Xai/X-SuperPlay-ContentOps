"""V1 entry-point behaviour: the copy gate precedes audio, and a named narration
provider is never quietly replaced by edge-tts.

The failure this prevents: a project is narrated and composed without anyone
having read the copy, or a caller asks for a provider the build cannot reach and
receives an edge-tts render that looks successful.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import run_v1  # noqa: E402
from contentops.workflow import copy_review  # noqa: E402


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _project(temp: Path, *, video: bool = True) -> Path:
    script = temp / "script"
    script.mkdir()
    (script / "master.md").write_text("# script\n第一句\n", encoding="utf-8")
    shot = {"unit": "u1", "narration": "第一句", "caption": "第一句",
            "source_type": "motion" if video else "real_screenshot",
            "duration": 5.0}
    if video:
        shot["video"] = "project://work/motion/beat-00.mp4"
        shot["source"] = "project://work/motion/beat-00.mp4"
    else:
        shot["image"] = "project://sources/shot.png"
        shot["source"] = "project://sources/shot.png"
    (script / "storyboard.json").write_text(
        json.dumps({"size": "1080x1920", "shots": [shot]}, ensure_ascii=False),
        encoding="utf-8")
    # No receipts/ on purpose: the caller decides whether to approve.
    return temp


def _approve(project: Path) -> None:
    copy_review.decide(project, status_value="APPROVED", reviewer="test-reviewer",
                       opinion="fixture approval used to exercise the entry point",
                       reviewed_at="2026-11-01T00:00:00Z")


def test_a_missing_copy_review_blocks_before_any_audio():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        result = run_v1.run_easel(project)
        assert result["status"] == "BLOCKED", result
        assert result["stage"] == "copy_review", result
        assert not (project / "script" / "narration.txt").exists(), (
            "the gate must stop before the pipeline writes anything for the voice")


def test_a_named_provider_that_is_unreachable_is_refused():
    """No silent downgrade: asking for an unavailable provider must fail."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        result = run_v1.run_easel(project, voice_provider="minimax")
        assert result["status"] == "BLOCKED", result
        assert result["stage"] == "narration", result
        assert "refusing to fall back" in result["reason"], result


def test_existing_narration_without_a_receipt_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        audio = project / "work" / "voice.wav"
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(b"RIFF....WAVEfmt ")
        result = run_v1.run_easel(project, voice_provider="existing", narration=audio)
        assert result["status"] == "BLOCKED", result
        assert result["stage"] == "narration", result
        assert "receipt" in result["reason"], result


def test_existing_narration_bound_to_a_different_script_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        audio = project / "work" / "voice.wav"
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(b"RIFF....WAVEfmt ")
        receipt = project / "work" / "voice.receipt.json"
        receipt.write_text(json.dumps({
            "provider": "fixture", "model": "speech-2.8-hd",
            "display_text_sha256": _sha("a different script entirely"),
        }), encoding="utf-8")
        result = run_v1.run_easel(project, voice_provider="existing",
                                  narration=audio, narration_receipt=receipt)
        assert result["status"] == "BLOCKED", result
        assert "not bound to the current script" in result["reason"], result


def test_a_video_shot_survives_script_parsing():
    """V1's production path is storyboard-driven; it must not drop the clip."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp), video=True)
        shots = run_v1.parse_script_shots(project)
        assert len(shots) == 1
        assert shots[0].get("video") == "project://work/motion/beat-00.mp4"


def test_a_still_shot_still_parses():
    """The historical image-only project shape must keep working."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp), video=False)
        shots = run_v1.parse_script_shots(project)
        assert shots[0].get("image") == "project://sources/shot.png"
        assert "video" not in shots[0]


def main() -> int:
    tests = (test_a_missing_copy_review_blocks_before_any_audio,
             test_a_named_provider_that_is_unreachable_is_refused,
             test_existing_narration_without_a_receipt_is_refused,
             test_existing_narration_bound_to_a_different_script_is_refused,
             test_a_video_shot_survives_script_parsing,
             test_a_still_shot_still_parses)
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"All {len(tests)} V1 narration-source tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
