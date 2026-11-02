"""M5 must be able to place a video shot, and must never substitute a still or a
different voice when the declared one is unavailable.

The failure this prevents, twice over:

- M5 built its own storyboard with ``image`` and a literal ``"motion": "static"``,
  so a rendered clip in the manifest could not reach the composer at all;
- asking for a narration source the build could not reach returned a SAPI track
  that looked like a success.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import m5_production  # noqa: E402
from contentops.media import storyboard_adapter as adapter  # noqa: E402


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assets(temp: Path, *, video: bool = True) -> dict:
    media = temp / "work" / "media"
    media.mkdir(parents=True, exist_ok=True)
    name = "beat-00.mp4" if video else "beat-00.png"
    (media / name).write_bytes(b"placeholder bytes")
    return {"A1": {"repo_path": f"work/media/{name}",
                   "type": "video" if video else "screenshot"}}


def _lines():
    return [{"asset_id": "A1", "caption": "第一句", "narration": "第一句", "claim": "C1"}]


def _timings(seconds=5.0):
    return [{"duration": seconds}]


def test_a_video_asset_reaches_the_storyboard_as_a_clip():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        shots = adapter.build_shots(lines=_lines(), narration_lines=_timings(),
                                    assets=_assets(project), repo_root=project)
        assert shots[0]["video"] == "work/media/beat-00.mp4"
        assert shots[0]["source_type"] == "video"


def test_a_still_asset_is_not_labelled_a_clip():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        shots = adapter.build_shots(lines=_lines(), narration_lines=_timings(),
                                    assets=_assets(project, video=False), repo_root=project)
        assert "video" not in shots[0]
        assert shots[0]["image"] == "work/media/beat-00.png"


def test_the_composer_key_and_the_receipt_key_agree():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        shots = adapter.build_shots(lines=_lines(), narration_lines=_timings(4.25),
                                    assets=_assets(project), repo_root=project)
        assert shots[0]["duration"] == shots[0]["duration_s"] == 4.25


def test_a_missing_asset_stops_the_build():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        assets = _assets(project)
        (project / "work" / "media" / "beat-00.mp4").unlink()
        try:
            adapter.build_shots(lines=_lines(), narration_lines=_timings(),
                                assets=assets, repo_root=project)
        except adapter.StoryboardContractError as exc:
            assert "missing on disk" in str(exc), exc
        else:
            raise AssertionError("a missing clip must not silently become a still")


def test_a_non_positive_duration_stops_the_build():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        try:
            adapter.build_shots(lines=_lines(), narration_lines=_timings(0),
                                assets=_assets(project), repo_root=project)
        except adapter.StoryboardContractError:
            pass
        else:
            raise AssertionError("a zero-length shot must be refused")


def test_misaligned_lines_and_timings_stop_the_build():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        try:
            adapter.build_shots(lines=_lines(), narration_lines=[],
                                assets=_assets(project), repo_root=project)
        except adapter.StoryboardContractError as exc:
            assert "not aligned" in str(exc), exc
        else:
            raise AssertionError("an unaligned timeline must be refused")


def test_the_same_asset_placed_twice_stops_the_build():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        lines = _lines() + _lines()
        try:
            adapter.build_shots(lines=lines, narration_lines=_timings() + _timings(),
                                assets=_assets(project), repo_root=project)
        except adapter.StoryboardContractError as exc:
            assert "placed twice" in str(exc), exc
        else:
            raise AssertionError("a duplicated placement must be refused")


def _script():
    return {"lines": _lines()}


def test_an_unreachable_narration_provider_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        try:
            m5_production.stage_narration(project, _script(), provider="minimax")
        except m5_production.M5Blocked as exc:
            assert "refusing to fall back" in str(exc), exc
        else:
            raise AssertionError("an unavailable provider must not silently use SAPI")


def test_existing_narration_without_a_receipt_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        audio.write_bytes(b"RIFF")
        try:
            m5_production.stage_narration(project, _script(), provider="existing",
                                          narration_audio=audio)
        except m5_production.M5Blocked as exc:
            assert "narration-receipt" in str(exc), exc
        else:
            raise AssertionError("audio without provenance must be refused")


def test_existing_narration_bound_to_another_script_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        audio.write_bytes(b"RIFF")
        receipt = project / "narration.json"
        receipt.write_text(json.dumps({"text_sha256": _sha("other script"),
                                       "lines": _timings()}), encoding="utf-8")
        try:
            m5_production.stage_narration(project, _script(), provider="existing",
                                          narration_audio=audio,
                                          narration_receipt=receipt)
        except m5_production.M5Blocked as exc:
            assert "not bound to the current script" in str(exc), exc
        else:
            raise AssertionError("audio that speaks another script must be refused")


def test_existing_narration_without_line_timings_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        audio.write_bytes(b"RIFF")
        text = "\n".join(line["narration"] for line in _lines())
        receipt = project / "narration.json"
        receipt.write_text(json.dumps({"text_sha256": _sha(text)}), encoding="utf-8")
        try:
            m5_production.stage_narration(project, _script(), provider="existing",
                                          narration_audio=audio,
                                          narration_receipt=receipt)
        except m5_production.M5Blocked as exc:
            assert "per-line timings" in str(exc), exc
        else:
            raise AssertionError("audio without timings cannot drive subtitles")


def test_existing_narration_that_matches_is_reused_without_a_provider_call():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 4000)  # 0.5 s of silence
        text = "\n".join(line["narration"] for line in _lines())
        receipt = project / "narration.json"
        receipt.write_text(json.dumps({
            "engine": "speech-2.8-hd", "voice": "fixture",
            "text_sha256": _sha(text), "lines": _timings(0.5),
        }), encoding="utf-8")
        payload = m5_production.stage_narration(
            project, _script(), provider="existing",
            narration_audio=audio, narration_receipt=receipt)
        assert payload["voice_provider"] == "existing"
        assert payload["text_sha256"] == _sha(text)
        assert payload["network"] is False
        assert (project / "assets" / "voice" / "narration.wav").is_file()
        assert payload["duration_s"] > 0


def main() -> int:
    tests = (test_a_video_asset_reaches_the_storyboard_as_a_clip,
             test_a_still_asset_is_not_labelled_a_clip,
             test_the_composer_key_and_the_receipt_key_agree,
             test_a_missing_asset_stops_the_build,
             test_a_non_positive_duration_stops_the_build,
             test_misaligned_lines_and_timings_stop_the_build,
             test_the_same_asset_placed_twice_stops_the_build,
             test_an_unreachable_narration_provider_is_refused,
             test_existing_narration_without_a_receipt_is_refused,
             test_existing_narration_bound_to_another_script_is_refused,
             test_existing_narration_without_line_timings_is_refused,
             test_existing_narration_that_matches_is_reused_without_a_provider_call)
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"All {len(tests)} M5 motion-integration tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
