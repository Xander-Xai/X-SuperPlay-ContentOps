"""Focused consistency checks for motion copy and review-package bindings."""
from __future__ import annotations

import hashlib
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_code_animation_sample as builder  # noqa: E402
import package_code_animation_sample as packager  # noqa: E402


@contextmanager
def _project():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp)
        (path / "script").mkdir()
        yield path


def _srt(path: Path, texts: list[str]) -> None:
    blocks = []
    for index, text in enumerate(texts, 1):
        start = index - 1
        blocks.append(f"{index}\n00:00:{start:02d},000 --> 00:00:{start + 1:02d},000\n{text}")
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def test_motion_voice_and_timeline_match_approved_script_srt():
    with _project() as project:
        _srt(project / "script" / "approved.srt", ["第一句。", "第二句。"])
        voice = {"lines": [
            {"line": 1, "text": "第一句。"},
            {"line": 2, "text": "第二句。"},
        ]}
        segments = [
            {"type": "beat", "line": 1},
            {"type": "insert"},
            {"type": "beat", "line": 2},
        ]
        builder._validate_motion_copy(project, voice, segments, "easel", None)


def test_motion_gate_rejects_voice_or_timeline_drift_from_approved_srt():
    with _project() as project:
        _srt(project / "script" / "approved.srt", ["第一句。", "第二句。"])
        voice = {"lines": [
            {"line": 1, "text": "被改过的第一句。"},
            {"line": 2, "text": "第二句。"},
        ]}
        segments = [{"type": "beat", "line": 1}, {"type": "beat", "line": 2}]
        try:
            builder._validate_motion_copy(project, voice, segments, "easel", None)
        except SystemExit as exc:
            assert "approved script SRT" in str(exc)
        else:
            raise AssertionError("changed synthesized voice text passed the motion gate")
        segments.reverse()
        try:
            builder._validate_motion_copy(project, {"lines": [
                {"line": 1, "text": "第一句。"}, {"line": 2, "text": "第二句。"}]},
                segments, "easel", None)
        except SystemExit as exc:
            assert "voice order" in str(exc)
        else:
            raise AssertionError("reordered timeline voice passed the motion gate")


def test_presenter_text_must_match_contract_and_approved_srt():
    with _project() as project:
        _srt(project / "script" / "approved.srt", ["开场句。", "正文。"])
        voice = {"presenter": {"text": "错误开场。"},
                 "lines": [{"line": 1, "text": "正文。"}]}
        contract = {"variant": "eras", "text": "开场句。"}
        segments = [{"type": "presenter", "line": 0}, {"type": "beat", "line": 1}]
        try:
            builder._validate_motion_copy(project, voice, segments, "eras", contract)
        except SystemExit as exc:
            assert "presenter text" in str(exc)
        else:
            raise AssertionError("presenter text drift passed the motion gate")


def test_presenter_replaces_first_voice_line_without_duplicate():
    with _project() as project:
        _srt(project / "script" / "approved.srt", ["开场句。", "正文。"])
        voice = {"presenter": {"text": "开场句。"}, "lines": [
            {"line": 1, "text": "开场句。"}, {"line": 2, "text": "正文。"}]}
        contract = {"variant": "easel", "text": "开场句。", "replaces_line": 1}
        segments = [{"type": "presenter", "line": 0}, {"type": "beat", "line": 2}]
        builder._validate_motion_copy(project, voice, segments, "easel", contract)


def test_review_bundle_binds_timeline_contract_and_presenter_media_hashes():
    with _project() as project:
        (project / "motion" / "presenter").mkdir(parents=True)
        (project / "motion" / "timeline.json").write_text('{"segments": []}', encoding="utf-8")
        contract = project / "motion" / "presenter" / "contract.json"
        contract.write_text('{"text": "开场句。"}', encoding="utf-8")
        audio = project / "assets" / "voice" / "opening.wav"
        shot = project / "work" / "opening.mp4"
        audio.parent.mkdir(parents=True)
        shot.parent.mkdir(parents=True)
        audio.write_bytes(b"audio")
        shot.write_bytes(b"shot")
        sample = {"timeline": {"presenter": 1}, "voice": {"presenter": {
            "path": "project://assets/voice/opening.wav",
            "wav_sha256": hashlib.sha256(b"audio").hexdigest(),
            "shot": "project://work/opening.mp4",
            "shot_sha256": hashlib.sha256(b"shot").hexdigest(),
        }}}

        inputs = packager._motion_inputs(project, sample)
        assert set(inputs) == {"timeline", "presenter_contract", "presenter_audio", "presenter_media"}
        assert inputs["timeline"][1] == hashlib.sha256(
            (project / "motion" / "timeline.json").read_bytes()).hexdigest()
        assert inputs["presenter_contract"][1] == hashlib.sha256(contract.read_bytes()).hexdigest()
        assert inputs["presenter_audio"][1] == sample["voice"]["presenter"]["wav_sha256"]
        assert inputs["presenter_media"][1] == sample["voice"]["presenter"]["shot_sha256"]


def test_review_bundle_rejects_presenter_media_hash_drift():
    with _project() as project:
        (project / "motion").mkdir()
        (project / "motion" / "timeline.json").write_text('{"segments": []}', encoding="utf-8")
        (project / "motion" / "presenter").mkdir()
        (project / "motion" / "presenter" / "contract.json").write_text("{}", encoding="utf-8")
        media = project / "opening.wav"
        media.write_bytes(b"current")
        sample = {"timeline": {"presenter": 1}, "voice": {"presenter": {
            "path": "project://opening.wav", "wav_sha256": "not-current",
            "shot": "project://opening.wav", "shot_sha256": "not-current",
        }}}
        try:
            packager._motion_inputs(project, sample)
        except SystemExit as exc:
            assert "differs" in str(exc)
        else:
            raise AssertionError("presenter media hash drift entered the review bundle")


def main() -> int:
    tests = [test_motion_voice_and_timeline_match_approved_script_srt,
             test_motion_gate_rejects_voice_or_timeline_drift_from_approved_srt,
             test_presenter_text_must_match_contract_and_approved_srt,
             test_presenter_replaces_first_voice_line_without_duplicate,
             test_review_bundle_binds_timeline_contract_and_presenter_media_hashes,
             test_review_bundle_rejects_presenter_media_hash_drift]
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"All {len(tests)} code-animation consistency tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
