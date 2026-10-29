"""The presenter opening must not be able to disappear from a build.

Run: python tests/test_presenter_opening.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import presenter_opening as opening  # noqa: E402

TEXT = "这条视频，只讲一个问题。"


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _project(temp: str, *, contract=None, text=TEXT, wav=b"wav", shot=b"shot",
             verified=False) -> Path:
    project = Path(temp)
    (project / "motion" / "presenter").mkdir(parents=True)
    (project / "assets" / "voice").mkdir(parents=True)
    (project / "work" / "generated").mkdir(parents=True)
    (project / "receipts").mkdir(parents=True)
    (project / "assets" / "voice" / "opening.wav").write_bytes(wav)
    (project / "work" / "generated" / "shot.mp4").write_bytes(shot)
    voice = {"lines": [{"line": 1, "duration_s": 2.0}],
             "presenter": {"text": text,
                           "path": "project://assets/voice/opening.wav",
                           "wav_sha256": _sha(wav),
                           "shot": "project://work/generated/shot.mp4",
                           "shot_sha256": _sha(shot),
                           "speech_text_verified": verified}}
    (project / "receipts" / "voice-lines.json").write_text(
        json.dumps(voice, ensure_ascii=False), encoding="utf-8")
    if contract is not None:
        (project / "motion" / "presenter" / "contract.json").write_text(
            json.dumps(contract, ensure_ascii=False), encoding="utf-8")
    return project


CONTRACT = {"schema": "contentops.presenter-opening/v1", "variant": "eras",
            "clip": "p00", "text": TEXT, "max_share": 0.1}

SEGMENTS = [{"type": "presenter", "clip": "p00", "line": 0, "duration": 2.6},
            {"type": "beat", "clip": "p01", "line": 1, "duration": 2.0},
            # A real film is long enough that the opening is a small share; the
            # ceiling checks a proportion, so the fixture has to have one.
            {"type": "beat", "clip": "p02", "line": 2, "duration": 28.0}]


def test_a_project_without_a_contract_is_not_blocked():
    """The opening is opt-in; most projects never declare one."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        assert opening.load_contract(project) is None
        voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
        assert opening.problems(None, project, SEGMENTS, "eras", voice) == []


def test_a_declared_opening_missing_from_the_timeline_is_a_problem():
    """This is the failure the contract exists for: a film that ships without him."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, contract=CONTRACT)
        voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
        issues = opening.problems(CONTRACT, project, SEGMENTS[1:], "eras", voice)
        assert len(issues) == 1 and "0 presenter segment" in issues[0], issues


def test_the_presenter_segment_must_render_the_declared_clip():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, contract=CONTRACT)
        voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
        segments = [dict(SEGMENTS[0], clip="p07"), SEGMENTS[1]]
        issues = opening.problems(CONTRACT, project, segments, "eras", voice)
        assert any("renders 'p07'" in issue for issue in issues), issues


def test_a_file_that_no_longer_matches_its_recorded_hash_is_a_problem():
    """A re-rendered shot must update the receipt, not slide past it."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, contract=CONTRACT)
        voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
        (project / "work" / "generated" / "shot.mp4").write_bytes(b"a different shot")
        issues = opening.problems(CONTRACT, project, SEGMENTS, "eras", voice)
        assert any("generated shot" in issue and "sha256" in issue for issue in issues), issues


def test_a_missing_opening_asset_is_named():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, contract=CONTRACT)
        voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
        (project / "assets" / "voice" / "opening.wav").unlink()
        issues = opening.problems(CONTRACT, project, SEGMENTS, "eras", voice)
        assert any("missing opening audio" in issue for issue in issues), issues


def test_voice_without_a_presenter_block_reports_once():
    """No block means no words and no audio; one clear issue beats a cascade."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, contract=CONTRACT)
        issues = opening.problems(CONTRACT, project, SEGMENTS, "eras", {"lines": []})
        assert len(issues) == 1 and "no presenter block" in issues[0], issues


def test_a_contract_for_another_variant_does_not_block_this_film():
    """The baseline must not be stopped by a declaration about the eras film."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, contract=CONTRACT)
        voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
        assert opening.problems(CONTRACT, project, SEGMENTS[1:], "easel", voice) == []


def test_requiring_verification_blocks_an_unverified_line():
    with tempfile.TemporaryDirectory() as temp:
        contract = dict(CONTRACT, require_speech_verified=True)
        project = _project(temp, contract=contract, verified=False)
        voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
        issues = opening.problems(contract, project, SEGMENTS, "eras", voice)
        assert any("speech_text_verified" in issue for issue in issues), issues


def test_the_share_ceiling_is_enforced_against_the_whole_film():
    with tempfile.TemporaryDirectory() as temp:
        contract = dict(CONTRACT, max_share=0.1)
        project = _project(temp, contract=contract)
        voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
        segments = [dict(SEGMENTS[0], duration=5.0), SEGMENTS[1]]
        issues = opening.problems(contract, project, segments, "eras", voice)
        assert any("above the" in issue for issue in issues), issues


def test_a_matching_declaration_is_ready():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, contract=CONTRACT, verified=False)
        voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
        assert opening.problems(CONTRACT, project, SEGMENTS, "eras", voice) == []


def _voice(verified=False):
    return {"presenter": {"text": TEXT, "speech_text_verified": verified}}


def test_a_passing_transcript_flips_the_flag_and_keeps_the_evidence():
    voice = _voice(False)
    verdict = {"status": "NO_PROBLEM_DETECTED", "role": "DETECTOR_ONLY",
               "coverage": 1.0, "transcript": "这条视频只讲一个问题。"}
    assert opening.apply_verdict(voice, verdict, verified_on="2026-10-28") is True
    block = voice["presenter"]
    assert block["speech_text_verified"] is True
    assert block["speech_check"]["coverage"] == 1.0
    assert block["speech_check"]["model"] == "asr-1.0"
    assert block["speech_check"]["checked_on"] == "2026-10-28"


def test_a_skipped_or_failing_check_never_verifies_the_line():
    """'We could not check' is not 'the words are right'."""
    for status in ("SKIPPED", "DETECTED_PROBLEM"):
        voice = _voice(False)
        verdict = {"status": status, "coverage": 0.4, "transcript": "别的话",
                   "detail": "cli unavailable"}
        opening.apply_verdict(voice, verdict, verified_on="2026-10-28")
        assert voice["presenter"]["speech_text_verified"] is False, status
        assert voice["presenter"]["speech_check"]["status"] == status, status


def test_a_repeat_verdict_with_the_same_result_is_not_a_change():
    voice = _voice(False)
    verdict = {"status": "NO_PROBLEM_DETECTED", "coverage": 1.0, "transcript": TEXT}
    assert opening.apply_verdict(voice, verdict, verified_on="2026-10-28") is True
    assert opening.apply_verdict(voice, verdict, verified_on="2026-10-28") is False


def test_the_check_cli_reports_blocked_then_ready():
    """The operator-facing gate the workflow runs before composing."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, contract=CONTRACT)
        (project / "motion" / "timeline.json").write_text(
            json.dumps({"segments": SEGMENTS}, ensure_ascii=False), encoding="utf-8")
        assert opening.main([str(project)]) == 0
        (project / "motion" / "timeline.json").write_text(
            json.dumps({"segments": SEGMENTS[1:]}, ensure_ascii=False), encoding="utf-8")
        assert opening.main([str(project)]) == 1


def test_writing_a_verdict_does_not_reformat_the_receipt():
    """A verified flag must show up as two fields, not a whole-file diff."""
    path = ROOT / "projects" / "easel-fi-what-is-agent" / "receipts" / "voice-lines.json"
    text = path.read_text(encoding="utf-8")
    assert opening._dumps(json.loads(text)) + "\n" == text


def test_the_other_pipeline_refuses_an_opening_it_cannot_place():
    """run_v1 would otherwise ship the film without him and look complete."""
    import run_v1

    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, contract=CONTRACT)
        (project / "project.yaml").write_text("title: t\n", encoding="utf-8")
        result = run_v1.run(project)
        assert result["status"] == "BLOCKED", result
        assert "build_code_animation_sample.py" in result["reason"], result


def test_the_real_project_honours_its_own_declaration():
    """The shipped project must satisfy the contract it ships."""
    project = ROOT / "projects" / "easel-fi-what-is-agent"
    contract = opening.load_contract(project)
    assert contract is not None, "the project declares a presenter opening"
    voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
    timeline = json.loads((project / "motion" / "timeline.json").read_text(encoding="utf-8"))
    segments = [segment for segment in timeline["segments"]
                if not segment.get("variant") or segment["variant"] == "eras"]
    issues = opening.problems(contract, project, segments, "eras", voice)
    # The audio and the generated shot are gitignored, so a clean checkout (and
    # every CI runner) lacks them. Absent media is not a contract violation —
    # but anything else still fails, so this cannot hide a broken declaration.
    host_local = bool(issues) and all(
        issue.startswith(("missing opening audio:", "missing generated shot:"))
        for issue in issues)
    if host_local:
        print("[skip] presenter opening: gitignored media absent on this checkout")
        return
    assert issues == [], issues


def main() -> int:
    tests = (
        test_a_project_without_a_contract_is_not_blocked,
        test_a_declared_opening_missing_from_the_timeline_is_a_problem,
        test_the_presenter_segment_must_render_the_declared_clip,
        test_a_file_that_no_longer_matches_its_recorded_hash_is_a_problem,
        test_a_missing_opening_asset_is_named,
        test_voice_without_a_presenter_block_reports_once,
        test_a_contract_for_another_variant_does_not_block_this_film,
        test_requiring_verification_blocks_an_unverified_line,
        test_the_share_ceiling_is_enforced_against_the_whole_film,
        test_a_matching_declaration_is_ready,
        test_a_passing_transcript_flips_the_flag_and_keeps_the_evidence,
        test_a_skipped_or_failing_check_never_verifies_the_line,
        test_a_repeat_verdict_with_the_same_result_is_not_a_change,
        test_the_check_cli_reports_blocked_then_ready,
        test_writing_a_verdict_does_not_reformat_the_receipt,
        test_the_other_pipeline_refuses_an_opening_it_cannot_place,
        test_the_real_project_honours_its_own_declaration,
    )
    failures = []
    for test in tests:
        try:
            test()
            print(f"[ok] {test.__name__}")
        except AssertionError as exc:
            failures.append((test.__name__, str(exc)))
            print(f"[FAIL] {test.__name__}: {exc}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} presenter tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
